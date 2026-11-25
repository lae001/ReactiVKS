"""Вес мимики для каждого условия (none | glasses | beard | glasses_beard) при маршрутизации моделей.

Для изображений валидации и теста с синтетическими очками и бородой (fer_training.occlusions, тот же seed, что в
eval_occlusion.py) заново строится сетка лица MediaPipe – мимика под оправой и бородой искажается так же, как на
живом видео. CNN – RoutedClassifier (без признаков – ансамбль v1.0 + v1.1, с признаками – v1.1); условие
считается известным (детектор признаков проверен отдельно на CelebA). Голова мимики – из blendshape_head.json
устойчивой модели; закрытые зоны отключаются (BlendshapeHead.mask). Вес выбирается по accuracy на валидации,
тест – итоговые числа. Результат дописывается в blendshape_head.json (fusion_weights) и results/fusion_occlusion.json.

Запуск из ml/training:  uv run python scripts/tune_fusion_occlusion.py [--ferplus data/ferplus/fer2013new.csv]
(с --ferplus валидация и тест – с метками FER+, отчет – results/fusion_occlusion_ferplus.json)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from emotion_service.classifier import OnnxEmotionClassifier, RoutedClassifier
from emotion_service.fusion import BlendshapeHead, fuse
from emotion_service.labels import LABELS
from emotion_service.landmarks import BLENDSHAPE_NAMES, FaceMeshAnalyzer
from emotion_service.preprocessing import to_model_batch
from sklearn.metrics import f1_score

from fer_training.config import DataConfig
from fer_training.data import FER_SPLITS, build_splits, ferplus_labels, image_hashes, load_fer2013
from fer_training.occlusions import occlude_set

MODELS = Path(__file__).absolute().parents[2] / "models"
CONDITIONS = {"none": None, "glasses": "glasses", "beard": "beard", "glasses_beard": "glasses_beard"}
OCCLUDED = {"none": (), "glasses": ("glasses",), "beard": ("beard",), "glasses_beard": ("glasses", "beard")}
SURPRISE = LABELS.index("surprise")


def mesh_features(analyzer: FaceMeshAnalyzer, images: np.ndarray) -> np.ndarray:
    out = np.full((len(images), len(BLENDSHAPE_NAMES)), np.nan, np.float32)
    for i, gray in enumerate(images):
        mesh = analyzer.analyze_crop(np.repeat(gray[:, :, None], 3, axis=2))
        if mesh is not None:
            out[i] = mesh.blendshape_vector()
    return out


def score(labels: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    preds = probs.argmax(1)
    return {
        "accuracy": round(float((preds == labels).mean()), 4),
        "macro_f1": round(float(f1_score(labels, preds, average="macro")), 4),
        "surprise_recall": round(float((preds[labels == SURPRISE] == SURPRISE).mean()), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ferplus", help="метки FER+ вместо исходных меток FER-2013")
    args = parser.parse_args()
    base = OnnxEmotionClassifier(MODELS / "emotion" / "model_card.json", threads=8)
    robust = OnnxEmotionClassifier(MODELS / "emotion-robust" / "model_card.json", threads=8)
    routed = RoutedClassifier(base, robust)
    head_path = MODELS / "emotion-robust" / "blendshape_head.json"
    head = BlendshapeHead.load(head_path)
    analyzer = FaceMeshAnalyzer(MODELS / "mediapipe" / "face_landmarker.task")

    # Мимика чистых изображений уже посчитана (extract_blendshapes.py) – по хешу.
    raw = np.load("data/fer2013/blendshapes.npz")
    fer = load_fer2013(Path("data/fer2013"))
    table = {h: r for sp in FER_SPLITS for h, r in zip(image_hashes(fer[sp].images), raw[sp], strict=True)}
    val = build_splits(DataConfig(ferplus=args.ferplus), 42, Path.cwd()).val
    test_images = np.concatenate([fer["public_test"].images, fer["private_test"].images])
    test_labels = np.concatenate([fer["public_test"].labels, fer["private_test"].labels])
    test_points = np.concatenate([fer["public_test"].landmarks, fer["private_test"].landmarks])
    if args.ferplus:
        plus = ferplus_labels(args.ferplus)
        test_labels = np.concatenate([plus["public_test"], plus["private_test"]])
        keep = test_labels >= 0
        test_images, test_labels, test_points = test_images[keep], test_labels[keep], test_points[keep]
    splits = {"val": (val.images, val.labels, val.landmarks, 11), "test": (test_images, test_labels, test_points, 7)}

    def predict(images: np.ndarray, occluded: bool) -> np.ndarray:
        batch = to_model_batch(list(images))
        mask = np.full(len(batch), occluded)
        return np.concatenate([routed.predict(batch[i : i + 64], mask[i : i + 64]) for i in range(0, len(batch), 64)])

    data: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for split, (images, labels, points, seed) in splits.items():
        for condition, occlusion in CONDITIONS.items():
            x = images if occlusion is None else occlude_set(images, points, occlusion, seed=seed)
            if occlusion is None:
                nan = np.full(len(BLENDSHAPE_NAMES), np.nan, np.float32)
                feats = np.stack([table.get(h, nan) for h in image_hashes(x)])
            else:
                feats = mesh_features(analyzer, x)
            data[(split, condition)] = (predict(x, occlusion is not None), feats, labels)
            print(f"{split}/{condition}: сетка построена для {np.mean(~np.isnan(feats[:, 0])):.3f}", flush=True)

    def fused(split: str, condition: str, weight: float) -> np.ndarray:
        cnn, feats, _ = data[(split, condition)]
        out = cnn.copy()
        ok = ~np.isnan(feats[:, 0])
        masked = head.mask(feats[ok], OCCLUDED[condition])
        out[ok] = fuse(cnn[ok], head.predict(masked), weight)
        return out

    weights: dict[str, float] = {}
    report: dict[str, object] = {}
    grid = [round(w, 2) for w in np.arange(0, 0.75, 0.05)]
    for condition in CONDITIONS:
        val_labels = data[("val", condition)][2]
        best = max(grid, key=lambda w: (fused("val", condition, w).argmax(1) == val_labels).mean())
        weights[condition] = best
        report[condition] = {
            "weight": best,
            "val": {
                "cnn": score(val_labels, data[("val", condition)][0]),
                "fused": score(val_labels, fused("val", condition, best)),
            },
            "test": {
                "cnn": score(data[("test", condition)][2], data[("test", condition)][0]),
                "fused": score(data[("test", condition)][2], fused("test", condition, best)),
            },
        }  # fmt: skip
        print(condition, json.dumps(report[condition], ensure_ascii=False), flush=True)

    card = json.loads(head_path.read_text(encoding="utf-8"))
    card["fusion_weights"] = weights
    card["fusion_weight"] = weights["none"]
    card["occlusion_report"] = report
    head_path.write_text(json.dumps(card, ensure_ascii=False, indent=1), "utf-8")
    Path("results").mkdir(exist_ok=True)
    name = "fusion_occlusion_ferplus.json" if args.ferplus else "fusion_occlusion.json"
    Path("results", name).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    main()
