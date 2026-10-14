"""Общий препроцессинг лица: один и тот же код в сервисе и в обучении (ml/training).

Каноническое представление лица – кроп 48×48 в оттенках серого. Это родной формат FER-2013 (основной датасет и тест
целевой метрики), поэтому кадр видеовстречи приводится к тому же виду, что и обучающие изображения, и расхождение
«обучение ↔ инференс» не возникает.

Параметры кропа подобраны на валидации FER-2013, прогнанной через детектор (ml/training/scripts/calibrate_crop.py):
рамка YuNet по высоте ≈ 1,03 стороны кадрирования FER, по ширине ≈ 0,81, поэтому квадрат со стороной
max(w, h) × 0,85 вокруг центра рамки дает accuracy 0,688 против 0,685 на исходных изображениях; прежний кроп
(× 1,1 с поворотом по глазам) – 0,640, а полнота surprise падала с 0,80 до 0,65. Поворот по линии глаз отключен:
лица FER-2013 не выровнены по наклону, модель учится на наклонах ±15° через аугментации. Увеличение до входа сети
и нормализация ImageNet встроены в саму модель (ONNX), сервис их не повторяет.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np

CROP_SIZE: Final[int] = 48
PREPROCESSING_ID: Final[str] = "yunet-crop-gray48-v2"
# Отрицательный запас: кроп плотнее рамки YuNet, как кадрирование FER-2013 (см. docstring модуля).
DEFAULT_MARGIN: Final[float] = -0.15


@dataclass(frozen=True, slots=True)
class FaceBox:
    """Лицо на кадре: рамка в пикселях, уверенность детектора и 5 опорных точек (глаза, нос, уголки рта)."""

    x: float
    y: float
    w: float
    h: float
    score: float
    landmarks: np.ndarray | None = None  # (5, 2): глаз, глаз, нос, уголок рта, уголок рта

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def to_gray(image: np.ndarray) -> np.ndarray:
    """RGB (H, W, 3) или серое (H, W) → серое uint8."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def eye_angle(landmarks: np.ndarray | None) -> float:
    """Угол линии глаз в градусах (0 – глаза на одной горизонтали)."""
    if landmarks is None:
        return 0.0
    a, b = landmarks[0], landmarks[1]
    left, right = (a, b) if a[0] <= b[0] else (b, a)
    return math.degrees(math.atan2(float(right[1] - left[1]), float(right[0] - left[0])))


def resize_crop(gray: np.ndarray, size: int = CROP_SIZE) -> np.ndarray:
    """Приведение готового кропа лица к канонической стороне: уменьшение – INTER_AREA, увеличение – линейное."""
    if gray.shape[0] == size and gray.shape[1] == size:
        return gray
    interpolation = cv2.INTER_AREA if min(gray.shape[:2]) > size else cv2.INTER_LINEAR
    return cv2.resize(gray, (size, size), interpolation=interpolation)


def align_crop(
    image: np.ndarray, face: FaceBox, margin: float = DEFAULT_MARGIN, size: int = CROP_SIZE, rotate: bool = False
) -> np.ndarray:
    """Квадратный кроп лица в каноническом виде (серое size×size); rotate – выравнивание глаз по горизонтали.

    Поворот выполняется вокруг центра рамки без масштабирования, уменьшение – отдельно через INTER_AREA: так мелкие
    детали лица не теряются на алиасинге, как при уменьшении внутри warpAffine.
    """
    gray = to_gray(image)
    side = max(face.w, face.h) * (1.0 + margin)
    side_px = max(int(round(side)), 1)
    cx, cy = face.center
    matrix = cv2.getRotationMatrix2D((cx, cy), eye_angle(face.landmarks) if rotate else 0.0, 1.0)
    # Сдвиг: центр лица переходит в центр кропа.
    matrix[0, 2] += side_px / 2 - cx
    matrix[1, 2] += side_px / 2 - cy
    crop = cv2.warpAffine(gray, matrix, (side_px, side_px), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return resize_crop(crop, size)


def to_model_batch(crops: list[np.ndarray]) -> np.ndarray:
    """Кропы uint8 (size, size) → вход модели float32 (N, 1, size, size) в диапазоне [0, 1]."""
    if not crops:
        return np.zeros((0, 1, CROP_SIZE, CROP_SIZE), dtype=np.float32)
    batch = np.stack(crops).astype(np.float32) / 255.0
    return batch[:, None, :, :]
