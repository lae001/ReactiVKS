"""Внимание участника: «Заинтересован» – долго смотрит в камеру, «Отвлечен» – отвернулся или ушел из кадра.

Это не эмоция и не результат модели: оценка по позе головы, взгляду и времени. Два источника позы:

- **сетка лица** (landmarks.FaceMesh, 478 точек): yaw / pitch в градусах по 3D-матрице MediaPipe и положение
  радужки в глазу (взгляд). Смотрит в камеру – голова в пределах MESH_MAX_YAW / MESH_MAX_PITCH от анфаса и радужка
  не у края глаза (|взгляд| ≤ MAX_GAZE). Нейтральные значения – медианы по FER-2013 (scripts/extract_blendshapes.py);
- **5 точек YuNet** (запасной вариант, если сетка не построена): yaw – смещение носа от середины глаз вдоль линии
  глаз, нормированное межглазным расстоянием (0 – анфас, ±0,5 – профиль, угол ≈ asin(2·yaw)); pitch – положение
  носа между линией глаз и рта, у анфаса ≈ 0,56. Взгляд не измеряется.

Интерес – экспоненциальное среднее признака «смотрит в камеру» с разными постоянными времени: растет медленно
(τ = 5 с – нужен долгий взгляд), падает быстро (τ = 2 с – отвлечение видно сразу). Заинтересован – интерес ≥ 0,8
(≈ 5 с взгляда с нейтрального уровня), отвлечен – ≤ 0,3 (≈ 2,5 с без взгляда после долгого внимания).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

AttentionState = Literal["engaged", "attentive", "distracted"]

# 5 точек YuNet.
MAX_YAW = 0.2  # ≈ 24° поворота
PITCH_RANGE = (0.45, 0.68)
# Сетка лица: нейтральная поза камеры и допуски.
MESH_YAW0 = 0.0
MESH_PITCH0 = 5.0  # медиана FER-2013: yaw −0,3°, pitch +5,3° (80 % – от −7° до +18°)
MESH_MAX_YAW = 25.0
MESH_MAX_PITCH = 20.0
MAX_GAZE = 0.35  # 98 % лиц FER-2013 – в пределах ±0,36


@dataclass(frozen=True, slots=True)
class HeadPose:
    yaw_deg: float
    pitch_deg: float | None  # None – у 5 точек угол наклона не оценивается
    gaze_x: float | None
    looking: bool
    source: Literal["mesh", "landmarks5"]


def mesh_pose(yaw_deg: float, pitch_deg: float, gaze_x: float | None) -> HeadPose:
    looking = (
        abs(yaw_deg - MESH_YAW0) <= MESH_MAX_YAW
        and abs(pitch_deg - MESH_PITCH0) <= MESH_MAX_PITCH
        and (gaze_x is None or abs(gaze_x) <= MAX_GAZE)
    )
    return HeadPose(yaw_deg, pitch_deg, gaze_x, looking, "mesh")


def head_pose(landmarks: np.ndarray) -> HeadPose | None:
    """Точки YuNet: глаз, глаз, нос, уголок рта, уголок рта (в пикселях кадра)."""
    eye_a, eye_b, nose, mouth_a, mouth_b = landmarks.astype(np.float64)
    left, right = (eye_a, eye_b) if eye_a[0] <= eye_b[0] else (eye_b, eye_a)
    eyes = (left + right) / 2
    mouth = (mouth_a + mouth_b) / 2
    axis = right - left
    distance = float(np.linalg.norm(axis))
    if distance < 1e-6:
        return None
    u = axis / distance
    v = np.array([-u[1], u[0]])
    if np.dot(mouth - eyes, v) < 0:
        v = -v
    mouth_depth = float(np.dot(mouth - eyes, v))
    if mouth_depth < 1e-6:
        return None
    yaw = float(np.dot(nose - eyes, u)) / distance
    pitch = float(np.dot(nose - eyes, v)) / mouth_depth
    looking = abs(yaw) <= MAX_YAW and PITCH_RANGE[0] <= pitch <= PITCH_RANGE[1]
    yaw_deg = math.degrees(math.asin(max(-1.0, min(1.0, 2 * yaw))))
    return HeadPose(yaw_deg, None, None, looking, "landmarks5")


@dataclass(frozen=True, slots=True)
class Attention:
    state: AttentionState
    interest: float  # «вероятность» заинтересованности; отвлеченность = 1 − interest
    looking: bool
    pose: HeadPose | None


class AttentionTracker:
    def __init__(
        self,
        rise_s: float = 5.0,
        fall_s: float = 2.0,
        engaged_at: float = 0.8,
        distracted_at: float = 0.3,
        initial: float = 0.5,
    ) -> None:
        self.rise_s = rise_s
        self.fall_s = fall_s
        self.engaged_at = engaged_at
        self.distracted_at = distracted_at
        self.initial = initial
        self._state: dict[str, tuple[float, float]] = {}  # участник → (интерес, время)

    def update(self, key: str, pose: HeadPose | None, now: float) -> Attention:
        looking = pose is not None and pose.looking
        interest, last = self._state.get(key, (self.initial, now))
        dt = max(0.0, now - last)
        target = 1.0 if looking else 0.0
        tau = self.rise_s if looking else self.fall_s
        interest = target + (interest - target) * math.exp(-dt / tau)
        self._state[key] = (interest, now)
        if interest >= self.engaged_at:
            state: AttentionState = "engaged"
        elif interest <= self.distracted_at:
            state = "distracted"
        else:
            state = "attentive"
        return Attention(state, round(interest, 4), looking, pose)

    def reset(self, key: str) -> None:
        self._state.pop(key, None)
