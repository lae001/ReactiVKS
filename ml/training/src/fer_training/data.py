"""Датасеты: загрузка в каноническое представление (серое 48×48, uint8) и разбиение train/val/test.

Разбиение (EMO-27):
- train / val – стратифицированное деление обучающей части (по умолчанию 90/10, фиксированный seed);
- test – FER-2013 PublicTest + PrivateTest (целевая метрика ТЗ), отдельно сообщается PrivateTest для сравнения
  с литературой; у RAF-DB – собственная тестовая часть.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from emotion_service.labels import LABELS, NUM_CLASSES
from emotion_service.preprocessing import CROP_SIZE, resize_crop
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset

from fer_training.config import DataConfig

log = logging.getLogger(__name__)

FER_SPLITS = {"train": "train.parquet", "public_test": "publicTest.parquet", "private_test": "privateTest.parquet"}
# RAF-DB basic: 1 Surprise, 2 Fear, 3 Disgust, 4 Happiness, 5 Sadness, 6 Anger, 7 Neutral → порядок LABELS.
RAFDB_TO_LABEL = {1: 5, 2: 2, 3: 1, 4: 3, 5: 4, 6: 0, 7: 6}
# Синонимы имен классов в каталогах датасетов (AffectNet, RAF-DB в виде папок и т. п.); contempt исключается.
FOLDER_ALIASES = {
    "anger": "angry",
    "disgusted": "disgust",
    "fearful": "fear",
    "happiness": "happy",
    "sadness": "sad",
    "surprised": "surprise",
    "neutrality": "neutral",
}
BLANK_STD = 2.0


@dataclass
class ImageSet:
    """Набор изображений в каноническом виде: images (N, 48, 48) uint8, labels (N,) int64."""

    images: np.ndarray
    labels: np.ndarray
    source: str

    def __len__(self) -> int:
        return len(self.labels)

    def subset(self, index: np.ndarray) -> ImageSet:
        return ImageSet(self.images[index], self.labels[index], self.source)

    def class_counts(self) -> np.ndarray:
        return np.bincount(self.labels, minlength=NUM_CLASSES)


def concat(sets: list[ImageSet], source: str) -> ImageSet:
    return ImageSet(np.concatenate([s.images for s in sets]), np.concatenate([s.labels for s in sets]), source)


def decode_gray(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("Не удалось декодировать изображение")
    return resize_crop(image, CROP_SIZE)


# ---------------------------------------------------------------------------
# FER-2013
# ---------------------------------------------------------------------------


def load_fer2013(root: str | Path) -> dict[str, ImageSet]:
    """Сплиты FER-2013 из parquet (raw/) с кешем в fer2013.npz – повторная загрузка занимает доли секунды."""
    root = Path(root)
    cache = root / "fer2013.npz"
    if cache.exists():
        with np.load(cache) as packed:
            return {
                name: ImageSet(packed[f"{name}_images"], packed[f"{name}_labels"], f"fer2013/{name}")
                for name in FER_SPLITS
            }
    sets: dict[str, ImageSet] = {}
    for name, filename in FER_SPLITS.items():
        frame = pd.read_parquet(root / "raw" / filename)
        images = np.stack([decode_gray(cell["bytes"]) for cell in frame["image"]])
        sets[name] = ImageSet(images, frame["label"].to_numpy(dtype=np.int64), f"fer2013/{name}")
        log.info("FER-2013 %s: %d изображений", name, len(sets[name]))
    np.savez_compressed(cache, **{f"{n}_{k}": getattr(s, k) for n, s in sets.items() for k in ("images", "labels")})
    return sets


def is_blank(images: np.ndarray, threshold: float = BLANK_STD) -> np.ndarray:
    """Однотонные изображения (в FER-2013 есть пустые кадры без лица)."""
    return images.reshape(len(images), -1).std(axis=1) < threshold


def image_hashes(images: np.ndarray) -> list[str]:
    return [hashlib.blake2b(img.tobytes(), digest_size=12).hexdigest() for img in images]


# ---------------------------------------------------------------------------
# RAF-DB и каталоги с классами
# ---------------------------------------------------------------------------


def load_rafdb(root: str | Path) -> dict[str, ImageSet]:
    """RAF-DB basic: выровненные лица 100×100 → канонический вид, сплиты train/test из list_patition_label.txt."""
    root = Path(root)
    lines = (root / "EmoLabel" / "list_patition_label.txt").read_text(encoding="utf-8").split()
    names, raw_labels = lines[0::2], lines[1::2]
    buckets: dict[str, tuple[list[np.ndarray], list[int]]] = {"train": ([], []), "test": ([], [])}
    for name, raw in zip(names, raw_labels, strict=True):
        split = "train" if name.startswith("train") else "test"
        path = root / "Image" / "aligned" / name.replace(".jpg", "_aligned.jpg")
        buckets[split][0].append(decode_gray(path.read_bytes()))
        buckets[split][1].append(RAFDB_TO_LABEL[int(raw)])
    return {
        split: ImageSet(np.stack(imgs), np.asarray(labels, dtype=np.int64), f"rafdb/{split}")
        for split, (imgs, labels) in buckets.items()
    }


def load_folder(root: str | Path) -> dict[str, ImageSet]:
    """Раскладка <root>/<split>/<класс>/*.(jpg|png); классы вне LABELS (например, contempt) пропускаются."""
    root = Path(root)
    result: dict[str, ImageSet] = {}
    for split_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        images: list[np.ndarray] = []
        labels: list[int] = []
        for class_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
            name = FOLDER_ALIASES.get(class_dir.name.lower(), class_dir.name.lower())
            if name not in LABELS:
                log.info("Класс %s пропущен", class_dir)
                continue
            for path in sorted(class_dir.glob("*")):
                if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    images.append(decode_gray(path.read_bytes()))
                    labels.append(LABELS.index(name))
        if images:
            result[split_dir.name] = ImageSet(
                np.stack(images), np.asarray(labels, dtype=np.int64), f"{root.name}/{split_dir.name}"
            )
    return result


# ---------------------------------------------------------------------------
# Разбиение
# ---------------------------------------------------------------------------


@dataclass
class Splits:
    train: ImageSet
    val: ImageSet
    # Именованные тестовые наборы: fer2013 (Public + Private) – целевая метрика, остальные – справочно.
    tests: dict[str, ImageSet]


def stratified_split(data: ImageSet, val_fraction: float, seed: int) -> tuple[ImageSet, ImageSet]:
    index = np.arange(len(data))
    train_idx, val_idx = train_test_split(index, test_size=val_fraction, random_state=seed, stratify=data.labels)
    return data.subset(np.sort(train_idx)), data.subset(np.sort(val_idx))


def deduplicate(train: ImageSet, exclude: list[ImageSet]) -> tuple[ImageSet, dict[str, int]]:
    """Очистка обучающей части по точным копиям изображений (EDA, раздел 4).

    - копии тестовых изображений удаляются: иначе модель видит тест при обучении и accuracy завышается;
    - группы копий с разными метками удаляются целиком: это шум разметки;
    - из согласованных копий остается одна, чтобы копия не попала одновременно в train и val.
    """
    test_hashes = {h for s in exclude for h in image_hashes(s.images)}
    groups: dict[str, list[int]] = {}
    for index, digest in enumerate(image_hashes(train.images)):
        groups.setdefault(digest, []).append(index)
    keep: list[int] = []
    stats = {"leaked_into_test": 0, "label_conflicts": 0, "duplicates": 0}
    for digest, members in groups.items():
        if digest in test_hashes:
            stats["leaked_into_test"] += len(members)
        elif len(set(train.labels[members].tolist())) > 1:
            stats["label_conflicts"] += len(members)
        else:
            keep.append(members[0])
            stats["duplicates"] += len(members) - 1
    return train.subset(np.sort(np.asarray(keep))), stats


def build_splits(cfg: DataConfig, seed: int, base_dir: Path | None = None) -> Splits:
    def resolve(path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() or base_dir is None else base_dir / p

    fer = load_fer2013(resolve(cfg.fer2013))
    fer_train = fer["train"]
    tests = {
        "fer2013": concat([fer["public_test"], fer["private_test"]], "fer2013/test"),
        "fer2013_private": fer["private_test"],
    }
    if cfg.drop_blank:
        keep = ~is_blank(fer_train.images)
        log.info("FER-2013: исключено однотонных изображений из обучения: %d", int((~keep).sum()))
        fer_train = fer_train.subset(np.flatnonzero(keep))
    if cfg.dedup:
        fer_train, stats = deduplicate(fer_train, [tests["fer2013"]])
        log.info("FER-2013, дедупликация обучения: %s", stats)
    train, val = stratified_split(fer_train, cfg.val_fraction, seed)
    trains, vals = [train], [val]

    extra: list[tuple[str, Callable[[str | Path], dict[str, ImageSet]], str]] = []
    if cfg.rafdb:
        extra.append(("rafdb", load_rafdb, cfg.rafdb))
    extra.extend((Path(f).name, load_folder, f) for f in cfg.folders)
    for name, loader, path in extra:
        parts = loader(resolve(path))
        if "val" in parts or "validation" in parts:
            trains.append(parts["train"])
            vals.append(parts["val"] if "val" in parts else parts["validation"])
        else:
            t, v = stratified_split(parts["train"], cfg.val_fraction, seed)
            trains.append(t)
            vals.append(v)
        if "test" in parts:
            tests[name] = parts["test"]

    return Splits(train=concat(trains, "train"), val=concat(vals, "val"), tests=tests)


# ---------------------------------------------------------------------------
# Dataset для DataLoader
# ---------------------------------------------------------------------------


class FaceDataset(Dataset[tuple[torch.Tensor, int]]):
    """Отдает (1, 48, 48) float32 в [0, 1] – ровно тот вход, что получает модель в сервисе."""

    def __init__(self, data: ImageSet, transform: Callable[..., dict[str, np.ndarray]] | None = None) -> None:
        self.data = data
        self.transform = transform

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        image = self.data.images[index]
        if self.transform is not None:
            image = self.transform(image=image)["image"]
        tensor = torch.from_numpy(np.ascontiguousarray(image)).float().div_(255.0).unsqueeze(0)
        return tensor, int(self.data.labels[index])


def to_tensor(images: np.ndarray) -> torch.Tensor:
    """Пакет без аугментаций для быстрой оценки: (N, 48, 48) uint8 → (N, 1, 48, 48) float32."""
    return torch.from_numpy(images).float().div_(255.0).unsqueeze(1)
