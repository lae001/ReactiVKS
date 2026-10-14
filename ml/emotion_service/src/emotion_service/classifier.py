"""Классификатор эмоций: ONNX-модель + model_card.json. Новая модель = новый файл и карточка, без изменения кода."""

from __future__ import annotations

import json
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
