"""Детектор лиц. Основной – YuNet (OpenCV Zoo, MIT): быстрый на CPU и дает 5 опорных точек для выравнивания.

Выбор детектора обоснован замером в docs/ml/face-detector.md (EMO-44).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from emotion_service.preprocessing import FaceBox


class FaceDetector(Protocol):
    def detect(self, image: np.ndarray) -> list[FaceBox]:
        """Лица на RGB-кадре (H, W, 3), по убыванию площади."""
        ...


class YuNetDetector:
    """cv2.FaceDetectorYN. Экземпляр не потокобезопасен: один на поток конвейера."""

    def __init__(self, model_path: str | Path, score_threshold: float = 0.6, nms_threshold: float = 0.3) -> None:
        self._detector = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), score_threshold, nms_threshold, 50)
        self._size: tuple[int, int] = (320, 320)

    def detect(self, image: np.ndarray) -> list[FaceBox]:
        height, width = image.shape[:2]
        if (width, height) != self._size:
            self._detector.setInputSize((width, height))
            self._size = (width, height)
        # YuNet обучен на BGR.
        # Заглушки типов OpenCV не отражают, что без лиц detect возвращает None.
        faces: np.ndarray | None = self._detector.detect(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))[1]
        if faces is None:
            return []
        boxes = [
            FaceBox(
                x=float(f[0]),
                y=float(f[1]),
                w=float(f[2]),
                h=float(f[3]),
                score=float(f[14]),
                landmarks=np.asarray(f[4:14], dtype=np.float32).reshape(5, 2),
            )
            for f in faces
        ]
        return sorted(boxes, key=lambda b: b.area, reverse=True)
