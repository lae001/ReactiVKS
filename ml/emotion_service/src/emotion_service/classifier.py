"""Классификатор эмоций: ONNX-модель + model_card.json. Новая модель = новый файл и карточка, без изменения кода."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import onnxruntime as ort

from emotion_service.labels import LABELS
from emotion_service.preprocessing import PREPROCESSING_ID


class EmotionClassifier(Protocol):
    labels: tuple[str, ...]
    model_version: str

    def predict(self, faces: np.ndarray) -> np.ndarray:
        """(N, 1, 48, 48) float32 в [0, 1] → (N, 7) вероятности в порядке labels."""
        ...


@dataclass(frozen=True)
class ModelCard:
    model_version: str
    labels: tuple[str, ...]
    preprocessing: str
    onnx_file: str
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> ModelCard:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            model_version=raw["model_version"],
            labels=tuple(raw["labels"]),
            preprocessing=raw["preprocessing"],
            onnx_file=raw["onnx"]["file"],
            raw=raw,
        )


class OnnxEmotionClassifier:
    def __init__(self, card_path: str | Path, threads: int = 2, providers: list[str] | None = None) -> None:
        card_path = Path(card_path)
        card = ModelCard.load(card_path)
        if card.labels != LABELS:
            raise ValueError(f"Порядок классов модели {card.labels} не совпадает с контрактом {LABELS}")
        if card.preprocessing != PREPROCESSING_ID:
            raise ValueError(f"Модель обучена с препроцессингом {card.preprocessing}, сервис – {PREPROCESSING_ID}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(card_path.parent / card.onnx_file), options, providers=providers or ["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name
        self.labels = card.labels
        self.model_version = card.model_version

    def predict(self, faces: np.ndarray) -> np.ndarray:
        if len(faces) == 0:
            return np.zeros((0, len(self.labels)), dtype=np.float32)
        probs: np.ndarray = self._session.run(None, {self._input: faces.astype(np.float32, copy=False)})[0]
        return probs


class RoutedClassifier:
    """Выбор модели по внешним признакам лица (experiments.md, §9): решение принято по валидации.

    - лицо без очков и бороды – среднее вероятностей базовой (v1.0) и устойчивой (v1.1) моделей: ансамбль точнее
      каждой (val 0,709 против 0,695 / 0,692);
    - очки и/или борода – только устойчивая модель, обученная с синтетическими очками и бородой (val с очками
      0,662 против 0,649 у ансамбля, с бородой 0,636 против 0,601).
    """

    def __init__(self, base: EmotionClassifier, robust: EmotionClassifier) -> None:
        if base.labels != robust.labels:
            raise ValueError("У моделей разный порядок классов")
        self.base = base
        self.robust = robust
        self.labels = base.labels
        self.model_version = f"{robust.model_version}+{base.model_version.rsplit('@', 1)[-1]}"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="base-model")

    def predict(self, faces: np.ndarray, occluded: np.ndarray | None = None) -> np.ndarray:
        """occluded – (N,) bool: у лица найдены очки или борода; None – признаки неизвестны (ансамбль для всех)."""
        if occluded is None:
            occluded = np.zeros(len(faces), dtype=bool)
        clean = ~occluded
        if not clean.any():
            return self.robust.predict(faces)
        # Модели независимы – считаются параллельно (ONNX Runtime отпускает GIL): такт короче почти вдвое.
        base_future = self._pool.submit(self.base.predict, faces[clean])
        robust = self.robust.predict(faces)
        result = robust.copy()
        result[clean] = (robust[clean] + base_future.result()) / 2
        return result
