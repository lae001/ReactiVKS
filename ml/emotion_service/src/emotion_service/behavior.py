"""Поведенческие сигналы встречи по сетке лица: согласие / несогласие (кивки, покачивания головой) и усталость.

Это не эмоции и не результат модели эмоций: правила по 3D-позе головы и мимическим коэффициентам MediaPipe за
скользящее окно (решение – docs/adr/ADR-013-emotion-groups-and-behavior.md).

**Кивок / покачивание.** За последние NOD_WINDOW_S секунд берется размах наклона (pitch) и поворота (yaw) головы
и число смен направления движения. Кивок – наклон меняется на ≥ MIN_SWING_DEG хотя бы дважды в разные стороны
(вниз-вверх) при почти неподвижном повороте; покачивание – то же по повороту. Такт анализа 2–5 кадров/с
меньше частоты кивка (1–3 Гц), поэтому форма движения не восстанавливается, но размах и смены направления
сохраняются: при 3 кадр/с кивок из 2–3 движений дает 2 и более смены. Надежнее при 5 кадр/с (ML_TARGET_FPS).

**Усталость.** PERCLOS – доля времени за FATIGUE_WINDOW_S с прикрытыми глазами (eyeBlink ≥ 0,5) – общепринятая
метрика сонливости (≥ 0,15 – признак усталости); зевки – рот открыт (jawOpen ≥ 0,55) непрерывно ≥ 1,2 с;
голова опущена (pitch выше нейтрального на ≥ 15°). Итоговый балл 0–1 – взвешенная сумма; «устал» – балл ≥ 0,5.
Очки мешают точкам век: если найдены очки, PERCLOS учитывается с половинным весом (glasses=True).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from emotion_service.attention import MESH_PITCH0
from emotion_service.landmarks import FaceMesh

Agreement = Literal["agree", "disagree", "none"]

NOD_WINDOW_S = 2.0
MIN_SWING_DEG = 6.0  # минимальное движение головы между точками разворота
CALM_AXIS_DEG = 8.0  # размах по другой оси, при котором движение еще считается чистым кивком / покачиванием
HOLD_S = 1.5  # сколько держится сигнал после последнего кивка / покачивания

FATIGUE_WINDOW_S = 30.0
EYES_CLOSED = 0.5
PERCLOS_TIRED = 0.15
YAWN_JAW = 0.55
YAWN_MIN_S = 1.2
YAWN_MEMORY_S = 60.0
HEAD_DOWN_DEG = 15.0
TIRED_AT = 0.5


def swings(values: np.ndarray, min_swing: float) -> int:
    """Число разворотов движения с амплитудой ≥ min_swing (зигзаг): вниз-вверх – 1, вниз-вверх-вниз – 2.

    Колебания меньше порога (шум позы, дрожание точек) не считаются.
    """
    count, direction, extreme = 0, 0, float(values[0]) if len(values) else 0.0
    for raw in values[1:]:
        value = float(raw)
        if direction == 0:
            if abs(value - extreme) >= min_swing:
                direction, extreme = (1 if value > extreme else -1), value
        elif direction > 0:
            if value > extreme:
                extreme = value
            elif extreme - value >= min_swing:
                count, direction, extreme = count + 1, -1, value
        else:
            if value < extreme:
                extreme = value
            elif value - extreme >= min_swing:
                count, direction, extreme = count + 1, 1, value
    return count


@dataclass(frozen=True, slots=True)
class Behavior:
    agreement: Agreement
    nod_score: float  # 0..1 – насколько уверенно виден кивок
    shake_score: float
    fatigue: Literal["alert", "tired"] | None  # None – мало данных или нет сетки лица
    fatigue_score: float | None
    perclos: float | None
    yawns_per_min: float | None


@dataclass
class _Fatigue:
    fatigue: Literal["alert", "tired"] | None
    fatigue_score: float | None
    perclos: float | None
    yawns_per_min: float | None


@dataclass
class _Track:
    pose: deque[tuple[float, float, float]]  # (время, yaw, pitch)
    eyes: deque[tuple[float, bool, bool]]  # (время, глаза прикрыты, голова опущена)
    yawn_started: float | None = None
    yawns: deque[float] = field(default_factory=deque)
    last_nod: float = -1e9
    last_shake: float = -1e9
    nod_score: float = 0.0
    shake_score: float = 0.0


class BehaviorTracker:
    def __init__(self, min_fatigue_s: float = 10.0) -> None:
        self.min_fatigue_s = min_fatigue_s
        self._tracks: dict[str, _Track] = {}

    def _track(self, key: str) -> _Track:
        track = self._tracks.get(key)
        if track is None:
            track = _Track(deque(), deque())
            self._tracks[key] = track
        return track

    def update(self, key: str, mesh: FaceMesh | None, now: float, glasses: bool = False) -> Behavior | None:
        if mesh is None:
            return None
        track = self._track(key)
        track.pose.append((now, mesh.yaw_deg, mesh.pitch_deg))
        while track.pose and now - track.pose[0][0] > NOD_WINDOW_S:
            track.pose.popleft()
        self._gestures(track, now)

        blink = (mesh.blendshapes.get("eyeBlinkLeft", 0.0) + mesh.blendshapes.get("eyeBlinkRight", 0.0)) / 2
        head_down = mesh.pitch_deg - MESH_PITCH0 >= HEAD_DOWN_DEG
        track.eyes.append((now, blink >= EYES_CLOSED, head_down))
        while track.eyes and now - track.eyes[0][0] > FATIGUE_WINDOW_S:
            track.eyes.popleft()
        self._yawn(track, mesh.blendshapes.get("jawOpen", 0.0), now)

        if now - track.last_nod <= HOLD_S and track.nod_score >= track.shake_score:
            agreement: Agreement = "agree"
        elif now - track.last_shake <= HOLD_S:
            agreement = "disagree"
        else:
            agreement = "none"
        fatigue = self._fatigue(track, now, glasses)
        decay = float(np.exp(-max(0.0, now - max(track.last_nod, track.last_shake)) / HOLD_S))
        return Behavior(
            agreement=agreement,
            nod_score=round(track.nod_score * decay if agreement == "agree" else 0.0, 3),
            shake_score=round(track.shake_score * decay if agreement == "disagree" else 0.0, 3),
            fatigue=fatigue.fatigue,
            fatigue_score=fatigue.fatigue_score,
            perclos=fatigue.perclos,
            yawns_per_min=fatigue.yawns_per_min,
        )

    def _gestures(self, track: _Track, now: float) -> None:
        if len(track.pose) < 4:
            return
        data = np.array([(y, p) for _, y, p in track.pose])
        yaw, pitch = data[:, 0], data[:, 1]
        yaw_range, pitch_range = float(np.ptp(yaw)), float(np.ptp(pitch))
        nod_turns, shake_turns = swings(pitch, MIN_SWING_DEG), swings(yaw, MIN_SWING_DEG)
        if nod_turns >= 2 and yaw_range <= max(CALM_AXIS_DEG, 0.6 * pitch_range):
            track.last_nod = now
            track.nod_score = min(1.0, pitch_range / 25.0 * min(1.0, nod_turns / 3))
        if shake_turns >= 2 and pitch_range <= max(CALM_AXIS_DEG, 0.6 * yaw_range):
            track.last_shake = now
            track.shake_score = min(1.0, yaw_range / 30.0 * min(1.0, shake_turns / 3))

    def _yawn(self, track: _Track, jaw_open: float, now: float) -> None:
        if jaw_open >= YAWN_JAW:
            if track.yawn_started is None:
                track.yawn_started = now
        else:
            if track.yawn_started is not None and now - track.yawn_started >= YAWN_MIN_S:
                track.yawns.append(now)
            track.yawn_started = None
        while track.yawns and now - track.yawns[0] > YAWN_MEMORY_S:
            track.yawns.popleft()

    def _fatigue(self, track: _Track, now: float, glasses: bool) -> _Fatigue:
        span = now - track.eyes[0][0] if track.eyes else 0.0
        if span < self.min_fatigue_s:
            return _Fatigue(None, None, None, None)
        perclos = sum(closed for _, closed, _ in track.eyes) / len(track.eyes)
        head_down = sum(down for _, _, down in track.eyes) / len(track.eyes)
        yawns = len(track.yawns) * 60.0 / min(YAWN_MEMORY_S, max(span, 1.0))
        eye_weight = 0.25 if glasses else 0.5  # оправа и блики сбивают точки век
        score = (
            eye_weight * min(1.0, perclos / (2 * PERCLOS_TIRED))
            + 0.35 * min(1.0, yawns / 2.0)
            + (0.65 - eye_weight) * min(1.0, head_down / 0.5)
        )
        return _Fatigue("tired" if score >= TIRED_AT else "alert", round(score, 3), round(perclos, 3), round(yawns, 2))

    def reset(self, key: str) -> None:
        self._tracks.pop(key, None)
