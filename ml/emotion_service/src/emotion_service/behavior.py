"""Поведенческие сигналы встречи по сетке лица: согласие / несогласие (кивки, покачивания головой) и усталость.

Это не эмоции и не результат модели эмоций: правила по 3D-позе головы и мимическим коэффициентам MediaPipe за
скользящее окно (решение – docs/adr/ADR-013-emotion-groups-and-behavior.md).

**Кивок / покачивание.** Кивок – за последние MOVE_WINDOW_S секунд наклон головы (pitch) отошел от начального
положения на ≥ NOD_DEG и вернулся к нему; покачивание – то же по повороту (yaw, ≥ SHAKE_DEG). Хватает одного
обычного кивка; серия «да-да» дает несколько срабатываний подряд. Голова должна начать и закончить движение в
покое, поэтому взгляд вниз или в сторону с возвратом через 1,5 с и больше, медленное покачивание при разговоре
и дрожание точек кивком не считаются. Такт 2–5 кадр/с: кивок длится 0,4–1 с, при 5 кадр/с в окно попадает
больше кадров движения и распознавание надежнее (симуляция – docs/adr/ADR-013).

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

MOVE_WINDOW_S = 1.5  # кивок туда и обратно укладывается в это время
NOD_DEG = 5.0  # отклонение наклона для кивка
SHAKE_DEG = 7.0  # отклонение поворота для покачивания (поворот головы шире и шумнее)
CALM_AXIS_DEG = 8.0  # размах по другой оси, при котором движение еще считается чистым кивком / покачиванием
HOLD_S = 2.5  # сколько держится сигнал после последнего кивка / покачивания

FATIGUE_WINDOW_S = 30.0
EYES_CLOSED = 0.5
PERCLOS_TIRED = 0.15
YAWN_JAW = 0.55
YAWN_MIN_S = 1.2
YAWN_MEMORY_S = 60.0
HEAD_DOWN_DEG = 15.0
TIRED_AT = 0.5


def back_and_forth(times: np.ndarray, values: np.ndarray, now: float, min_deg: float) -> float:
    """Наибольшее отклонение (градусы) движения «туда и обратно» за последние MOVE_WINDOW_S; 0 – движения нет.

    Движение – участок окна, где значение отошло от начала участка на ≥ min_deg и к концу участка вернулось
    (разница не больше половины отклонения): голова начала и закончила движение в одном положении. Участок ищется
    любой, поэтому серия «да-да» без пауз тоже находится. При частоте от 4 кадр/с соседние кадры усредняются
    попарно – дрожание точек вдвое меньше, а кивок (0,4–1 с) занимает несколько кадров и сохраняется.
    """
    mask = times >= now - MOVE_WINDOW_S
    window, stamps = values[mask], times[mask]
    if len(window) >= 4 and float(np.median(np.diff(stamps))) <= 0.25:
        window = (window[1:] + window[:-1]) / 2
        min_deg *= 0.8  # усреднение снижает и шум, и пик кивка
    best = 0.0
    for a in range(len(window) - 2):
        for b in range(a + 2, len(window)):
            swing = float(np.max(np.abs(window[a + 1 : b] - window[a])))
            if swing >= min_deg and abs(float(window[b] - window[a])) <= 0.5 * swing:
                best = max(best, swing)
    return best


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
        while track.pose and now - track.pose[0][0] > MOVE_WINDOW_S:
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
        if len(track.pose) < 3:
            return
        data = np.array(track.pose)
        times, yaw, pitch = data[:, 0], data[:, 1], data[:, 2]
        recent = times >= now - MOVE_WINDOW_S
        yaw_range, pitch_range = float(np.ptp(yaw[recent])), float(np.ptp(pitch[recent]))
        nod = back_and_forth(times, pitch, now, NOD_DEG)
        shake = back_and_forth(times, yaw, now, SHAKE_DEG)
        if nod and yaw_range <= max(CALM_AXIS_DEG, 0.6 * pitch_range):
            track.last_nod = now
            track.nod_score = min(1.0, nod / 12.0)
        if shake and pitch_range <= max(CALM_AXIS_DEG, 0.6 * yaw_range):
            track.last_shake = now
            track.shake_score = min(1.0, shake / 18.0)

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
