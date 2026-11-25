"""Плотная сетка лица: MediaPipe Face Landmarker – 478 точек (468 сетки + 10 радужки), 52 мимических коэффициента
(blendshapes, близки к единицам действия FACS: поднятие бровей, открытие рта, расширение глаз…) и 3D-поза головы.

Используется для внимания (поза головы по 3D-матрице и взгляд по положению радужки) и как второй источник
признаков эмоций (fusion.BlendshapeHead). Лицо находит YuNet; Face Landmarker получает увеличенную область вокруг
рамки – его собственный детектор рассчитан на крупное лицо и пропускает лица среднего размера
(docs/ml/face-detector.md).

Модель – face_landmarker.task (Apache 2.0), ml/models/fetch_models.sh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np

from emotion_service.preprocessing import FaceBox

BLENDSHAPE_NAMES: Final[tuple[str, ...]] = (
    "_neutral", "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff",
    "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel",
    "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker",
    "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft",
    "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "noseSneerLeft", "noseSneerRight",
)  # fmt: skip

# Индексы сетки MediaPipe для каждого глаза: уголки, верхнее и нижнее веко, центр радужки.
EYES: Final[tuple[tuple[int, int, int, int, int], ...]] = ((33, 133, 159, 145, 468), (362, 263, 386, 374, 473))
# Сторона, до которой увеличивается лицо перед Face Landmarker, и поля вокруг него.
FACE_SIDE: Final[int] = 192
CONTEXT: Final[float] = 1.6


@dataclass(frozen=True)
class FaceMesh:
    points: np.ndarray  # (478, 3): x, y в пикселях кадра, z – относительная глубина
    blendshapes: dict[str, float]
    yaw_deg: float  # поворот головы влево-вправо
    pitch_deg: float  # наклон вверх-вниз
    roll_deg: float  # наклон к плечу
    gaze_x: float | None  # положение радужки в глазу: −1 … 1 по горизонтали кадра, 0 – по центру
    gaze_y: float | None  # −1 – вверх, 1 – вниз

    def blendshape_vector(self) -> np.ndarray:
        return np.array([self.blendshapes.get(name, 0.0) for name in BLENDSHAPE_NAMES], dtype=np.float32)


def euler_from_matrix(matrix: np.ndarray) -> tuple[float, float, float]:
    """Углы (yaw, pitch, roll) в градусах из матрицы преобразования канонического лица MediaPipe."""
    r = matrix[:3, :3]
    yaw = math.degrees(math.atan2(r[0, 2], r[2, 2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -r[1, 2]))))
    roll = math.degrees(math.atan2(r[1, 0], r[1, 1]))
    return yaw, pitch, roll


def iris_gaze(points: np.ndarray) -> tuple[float | None, float | None]:
    """Среднее по двум глазам положение радужки между уголками (x) и веками (y), нормированное к −1 … 1."""
    xs, ys = [], []
    for corner_a, corner_b, lid_upper, lid_lower, iris_center in EYES:
        a, b = points[corner_a, :2], points[corner_b, :2]
        left, right = (a, b) if a[0] <= b[0] else (b, a)
        axis = right - left
        width = float(np.dot(axis, axis))
        upper, lower = points[lid_upper, :2], points[lid_lower, :2]
        height = float(lower[1] - upper[1])
        iris = points[iris_center, :2]
        if width < 1e-6:
            continue
        xs.append(2 * float(np.dot(iris - left, axis)) / width - 1)
        if height > 1e-6:
            ys.append(2 * float(iris[1] - upper[1]) / height - 1)
    return (float(np.mean(xs)) if xs else None, float(np.mean(ys)) if ys else None)


class FaceMeshAnalyzer:
    """Обертка над FaceLandmarker (режим IMAGE). Экземпляр не потокобезопасен: один на поток конвейера."""

    def __init__(self, model_path: str | Path, min_confidence: float = 0.3) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=1,
            min_face_detection_confidence=min_confidence,
            min_face_presence_confidence=min_confidence,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def _run(self, rgb: np.ndarray) -> tuple[np.ndarray, dict[str, float], np.ndarray] | None:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect(image)
        if not result.face_landmarks:
            return None
        height, width = rgb.shape[:2]
        points = np.array([[p.x * width, p.y * height, p.z * width] for p in result.face_landmarks[0]], np.float32)
        blendshapes = {c.category_name: float(c.score) for c in result.face_blendshapes[0]}
        return points, blendshapes, np.asarray(result.facial_transformation_matrixes[0])

    def _mesh(self, points: np.ndarray, blendshapes: dict[str, float], matrix: np.ndarray) -> FaceMesh:
        yaw, pitch, roll = euler_from_matrix(matrix)
        gaze_x, gaze_y = iris_gaze(points)
        return FaceMesh(points, blendshapes, yaw, pitch, roll, gaze_x, gaze_y)

    def analyze(self, frame: np.ndarray, face: FaceBox) -> FaceMesh | None:
        """Сетка лица по рамке детектора; точки – в координатах кадра."""
        side = max(face.w, face.h) * CONTEXT
        cx, cy = face.center
        out = int(round(FACE_SIDE * CONTEXT))
        scale = out / side
        # Аффинное преобразование: квадрат вокруг лица → out×out (края кадра дополняются повтором).
        matrix = np.array([[scale, 0, out / 2 - cx * scale], [0, scale, out / 2 - cy * scale]], np.float32)
        region = cv2.warpAffine(frame, matrix, (out, out), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        found = self._run(region)
        if found is None:
            return None
        points, blendshapes, pose = found
        points[:, 0] = (points[:, 0] - matrix[0, 2]) / scale
        points[:, 1] = (points[:, 1] - matrix[1, 2]) / scale
        points[:, 2] = points[:, 2] / scale
        return self._mesh(points, blendshapes, pose)

    def analyze_crop(self, face_rgb: np.ndarray) -> FaceMesh | None:
        """Сетка для уже вырезанного лица (обучающие изображения): лицо занимает центр, вокруг – поля."""
        h, w = face_rgb.shape[:2]
        return self.analyze(face_rgb, FaceBox(0, 0, w, h, 1.0))
