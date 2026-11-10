"""Внешние признаки лица, мешающие распознаванию эмоций: очки и борода (с усами и эспаньолкой).

Очки закрывают глаза и брови (оправа, блики, тонированные стекла), борода – рот, носогубные складки и подбородок.
Признаки определяет отдельная модель (CelebA, ml/training/scripts/train_attributes.py); конвейер учитывает их при
смешивании CNN с мимикой сетки лица (fusion.BlendshapeHead.fuse_with_attributes): коэффициенты закрытой зоны
не используются, вес мимики подобран для каждого условия отдельно (experiments.md, §9).

Признаки стабильны в течение встречи, поэтому вероятности сглаживаются по участнику (медленная EMA) и
определяются не на каждом такте. В события и в БД не попадают: это внешность человека, а не результат анализа
(ADR-009).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np
import onnxruntime as ort

from emotion_service.preprocessing import FaceBox

ATTRIBUTES: Final[tuple[str, ...]] = ("glasses", "beard")
CROP_SIDE: Final[int] = 96
# Кроп шире рамки YuNet и сдвинут вниз: борода и усы лежат ниже подбородка рамки, оправа – по бокам лица.
CROP_SCALE: Final[float] = 1.5
CROP_SHIFT_DOWN: Final[float] = 0.1


def attribute_crop(image: np.ndarray, face: FaceBox) -> np.ndarray:
    """RGB-кроп CROP_SIDE×CROP_SIDE (uint8) вокруг лица, края кадра дополняются повтором."""
    side = max(face.w, face.h) * CROP_SCALE
    cx, cy = face.center
    cy += CROP_SHIFT_DOWN * face.h
    scale = CROP_SIDE / side
    matrix = np.array([[scale, 0, CROP_SIDE / 2 - cx * scale], [0, scale, CROP_SIDE / 2 - cy * scale]], np.float32)
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.warpAffine(image, matrix, (CROP_SIDE, CROP_SIDE), flags=interpolation, borderMode=cv2.BORDER_REPLICATE)


@dataclass(frozen=True, slots=True)
class FaceAttributes:
    glasses: bool
    beard: bool
    glasses_prob: float
    beard_prob: float

    @property
    def occluded(self) -> tuple[str, ...]:
        return tuple(name for name in ATTRIBUTES if getattr(self, name))


class AttributeDetector:
    def __init__(self, card_path: str | Path, threads: int = 1, alpha: float = 0.3, interval_s: float = 2.0) -> None:
        card_path = Path(card_path)
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if tuple(card["attributes"]) != ATTRIBUTES:
            raise ValueError(f"Признаки модели {card['attributes']} не совпадают с {ATTRIBUTES}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(card_path.parent / card["onnx"]["file"]), options, providers=["CPUExecutionProvider"]
        )
        self.thresholds = np.array([card["thresholds"][name] for name in ATTRIBUTES], np.float32)
        self.model_version: str = card["model_version"]
        self.alpha = alpha
        # Очки и борода не меняются за секунды: модель вызывается для участника не чаще раза в interval_s
        # (нагрузочный замер, load-test.md: на такте из 10 лиц это экономит ≈ 25 мс).
        self.interval_s = interval_s
        self._state: dict[str, np.ndarray] = {}
        self._checked: dict[str, float] = {}

    def predict(self, crops: np.ndarray) -> np.ndarray:
        """(N, 96, 96, 3) uint8 → (N, 2) вероятности очков и бороды."""
        probs: np.ndarray = self._session.run(None, {"face": crops.astype(np.float32)})[0]
        return probs

    def update(self, key: str, image: np.ndarray, face: FaceBox, now: float | None = None) -> FaceAttributes:
        previous = self._state.get(key)
        last = self._checked.get(key)
        if previous is not None and now is not None and last is not None and now - last < self.interval_s:
            smoothed = previous
        else:
            probs = self.predict(attribute_crop(image, face)[None])[0]
            smoothed = probs if previous is None else self.alpha * probs + (1 - self.alpha) * previous
            self._state[key] = smoothed
            if now is not None:
                self._checked[key] = now
        flags = smoothed >= self.thresholds
        return FaceAttributes(
            bool(flags[0]), bool(flags[1]), round(float(smoothed[0]), 3), round(float(smoothed[1]), 3)
        )

    def reset(self, key: str) -> None:
        self._state.pop(key, None)
        self._checked.pop(key, None)
