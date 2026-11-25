"""Поведенческие сигналы встречи по сетке лица: согласие / несогласие, усталость, речь.

Это не эмоции и не результат модели эмоций: правила по 3D-позе головы и мимическим коэффициентам MediaPipe за
скользящее окно (решение – docs/adr/ADR-013-emotion-groups-and-behavior.md).

**Кивок / покачивание.** Кивок – за последние MOVE_WINDOW_S секунд наклон головы (pitch) отошел от начального
положения на ≥ NOD_DEG и вернулся к нему. Хватает одного обычного кивка; серия «да-да» дает несколько
срабатываний подряд. Покачивание «нет» – поворот (yaw) в **обе** стороны от начального положения (каждая – не
меньше SHAKE_SIDE_DEG, меньшая – не меньше половины большей, размах ≥ SHAKE_DEG) и возврат: отвести голову в одну
сторону и вернуть – это взгляд в сторону, а не несогласие. Отклонения больше MAX_GESTURE_DEG – тоже взгляд
(на соседа, в окно, на клавиатуру), а не жест. Голова должна начать и закончить движение в покое, поэтому
взгляд вниз или в сторону с возвратом через 1,5 с и больше, медленное покачивание при разговоре и дрожание
точек жестом не считаются. Такт 2–5 кадр/с: кивок длится 0,4–1 с, при 5 кадр/с в окно попадает
больше кадров движения и распознавание надежнее (симуляция – docs/adr/ADR-013).

**Усталость.** PERCLOS – доля времени за FATIGUE_WINDOW_S с прикрытыми глазами (eyeBlink ≥ 0,5) – общепринятая
метрика сонливости (≥ 0,15 – признак усталости); зевки – рот открыт (jawOpen ≥ 0,55) непрерывно ≥ 1,2 с;
голова опущена (pitch выше нейтрального на ≥ 15°). Итоговый балл 0–1 – взвешенная сумма; «устал» – балл ≥ 0,5.
Очки мешают точкам век: если найдены очки, PERCLOS учитывается с половинным весом (glasses=True).

**Речь.** По сетке лица: просвет между губами (точки 13–14) и ширина рта по уголкам (61–291), в долях расстояния
между внешними уголками глаз – не зависят от размера лица в кадре. Активность рта – колебания этих величин за
SPEECH_WINDOW_S: сумма изменений между кадрами за вычетом итогового сдвига, на один кадр. Речь – частое
открывание-закрывание; улыбка или открытый рот без движения дают сдвиг без колебаний и речью не считаются,
зевок исключается отдельно. Звук не анализируется: используется только признак «микрофон включен» из
LiveKit. Итог: speaking – рот двигается при включенном микрофоне; side_talk – рот двигается при выключенном
микрофоне (разговор с кем-то в комнате); silent – рот не двигается.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from emotion_service.attention import MESH_PITCH0
from emotion_service.landmarks import FaceMesh

Agreement = Literal["agree", "disagree", "none"]
Speech = Literal["speaking", "silent", "side_talk"]

MOVE_WINDOW_S = 1.5  # кивок туда и обратно укладывается в это время
SHAKE_WINDOW_S = 2.2  # «нет» (влево-вправо-назад) – дольше кивка
NOD_DEG = 5.0  # отклонение наклона для кивка
SHAKE_DEG = 9.0  # размах покачивания (влево + вправо)
SHAKE_SIDE_DEG = 3.5  # минимальное отклонение покачивания в каждую сторону
MAX_GESTURE_DEG = 30.0  # больше – голову отвели, чтобы посмотреть, а не жест
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

SPEECH_WINDOW_S = 2.0
SPEECH_FULL = 0.05  # колебание рта за кадр (в долях межглазного расстояния), при котором активность = 1
SPEECH_ON = 0.4  # активность, с которой рот «говорит»
SPEECH_OFF = 0.25  # гистерезис: ниже – молчит
SPEECH_HOLD_S = 1.0  # речь держится после последнего движения рта (паузы между словами)
MOUTH_UPPER, MOUTH_LOWER, MOUTH_LEFT, MOUTH_RIGHT, EYE_LEFT, EYE_RIGHT = 13, 14, 61, 291, 33, 263


def back_and_forth(
    times: np.ndarray,
    values: np.ndarray,
    now: float,
    min_deg: float,
    two_sided: bool = False,
    window_s: float = MOVE_WINDOW_S,
) -> float:
    """Наибольшее отклонение (градусы) движения «туда и обратно» за последние window_s секунд; 0 – движения нет.

    Движение – участок окна, где значение отошло от начала участка на ≥ min_deg и к концу участка вернулось
    (разница не больше половины отклонения): голова начала и закончила движение в одном положении. Участок ищется
    любой, поэтому серия «да-да» без пауз тоже находится. При частоте от 4 кадр/с соседние кадры усредняются
    попарно – дрожание точек вдвое меньше, а кивок (0,4–1 с) занимает несколько кадров и сохраняется.

    two_sided – покачивание «нет»: отклонения в обе стороны от начала (каждое ≥ SHAKE_SIDE_DEG, меньшее – не
    меньше половины большего), min_deg – размах от крайнего левого до крайнего правого положения; перед началом
    участка голова неподвижна (иначе возврат из поворота в сторону выглядел бы движением в другую сторону). Участки с
    отклонением больше MAX_GESTURE_DEG не считаются: так отводят голову, чтобы посмотреть.
    """
    mask = times >= now - window_s
    window, stamps = values[mask], times[mask]
    side = SHAKE_SIDE_DEG
    if len(window) >= 4 and float(np.median(np.diff(stamps))) <= 0.25:
        window = (window[1:] + window[:-1]) / 2
        min_deg *= 0.8  # усреднение снижает и шум, и пик кивка
        side *= 0.8
    best = 0.0
    for a in range(len(window) - 2):
        if two_sided and (a == 0 or abs(float(window[a] - window[a - 1])) > side):
            continue  # «нет» начинается из покоя
        for b in range(a + 2, len(window)):
            dev = window[a + 1 : b] - window[a]
            peak = float(np.max(np.abs(dev)))
            if peak > MAX_GESTURE_DEG or abs(float(window[b] - window[a])) > 0.5 * peak:
                continue
            if two_sided:
                right, left = float(dev.max()), float(-dev.min())
                if min(right, left) < max(side, max(right, left) / 2) or right + left < min_deg:
                    continue
                best = max(best, right + left)
            elif peak >= min_deg:
                best = max(best, peak)
    return best


def reversals(values: np.ndarray, min_swing: float) -> int:
    """Число разворотов движения с амплитудой ≥ min_swing (зигзаг): влево-вправо – 1, влево-вправо-влево – 2.

    Нужен для непрерывной серии «нет-нет-нет» без паузы, где начала в покое в окне уже нет. Отвести голову в одну
    сторону и вернуть – один разворот, поэтому не считается.
    """
    count, direction, extreme = 0, 0, float(values[0]) if len(values) else 0.0
    for raw in values[1:]:
        value = float(raw)
        if direction == 0:
            if abs(value - extreme) >= min_swing:
                direction, extreme = (1 if value > extreme else -1), value
        elif (value - extreme) * direction > 0:
            extreme = value
        elif abs(value - extreme) >= min_swing:
            count, direction, extreme = count + 1, -direction, value
    return count


def mouth_shape(points: np.ndarray) -> tuple[float, float] | None:
    """Просвет между губами и ширина рта по уголкам в долях расстояния между внешними уголками глаз."""
    eye = float(np.linalg.norm(points[EYE_LEFT, :2] - points[EYE_RIGHT, :2]))
    if eye < 1e-6:
        return None
    gap = float(np.linalg.norm(points[MOUTH_UPPER, :2] - points[MOUTH_LOWER, :2]))
    width = float(np.linalg.norm(points[MOUTH_LEFT, :2] - points[MOUTH_RIGHT, :2]))
    return gap / eye, width / eye


def oscillation(values: np.ndarray) -> float:
    """Колебание за кадр: сумма изменений между кадрами минус итоговый сдвиг, деленная на число шагов.

    Улыбка или открытый рот без движения – это сдвиг, а не колебание, и дают ≈ 0.
    """
    if len(values) < 3:
        return 0.0
    steps = np.abs(np.diff(values))
    return max(0.0, float(steps.sum() - abs(values[-1] - values[0]))) / len(steps)


@dataclass(frozen=True, slots=True)
class Behavior:
    agreement: Agreement
    nod_score: float  # 0..1 – насколько уверенно виден кивок
    shake_score: float
    fatigue: Literal["alert", "tired"] | None  # None – мало данных или нет сетки лица
    fatigue_score: float | None
    perclos: float | None
    yawns_per_min: float | None
    speech: Speech | None = None  # None – мало кадров
    mouth_activity: float | None = None  # 0..1
    mic_on: bool | None = None  # микрофон участника по данным LiveKit; None – неизвестно


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
    mouth: deque[tuple[float, float, float]] = field(default_factory=deque)  # (время, просвет, ширина)
    talking: bool = False
    last_talk: float = -1e9
    last_yawn: float = -1e9
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

    def update(
        self, key: str, mesh: FaceMesh | None, now: float, glasses: bool = False, mic_on: bool | None = None
    ) -> Behavior | None:
        if mesh is None:
            return None
        track = self._track(key)
        track.pose.append((now, mesh.yaw_deg, mesh.pitch_deg))
        while track.pose and now - track.pose[0][0] > SHAKE_WINDOW_S:
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
        speech, activity = self._speech(track, mesh, now, mic_on)
        decay = float(np.exp(-max(0.0, now - max(track.last_nod, track.last_shake)) / HOLD_S))
        return Behavior(
            agreement=agreement,
            nod_score=round(track.nod_score * decay if agreement == "agree" else 0.0, 3),
            shake_score=round(track.shake_score * decay if agreement == "disagree" else 0.0, 3),
            fatigue=fatigue.fatigue,
            fatigue_score=fatigue.fatigue_score,
            perclos=fatigue.perclos,
            yawns_per_min=fatigue.yawns_per_min,
            speech=speech,
            mouth_activity=activity,
            mic_on=mic_on,
        )

    def _gestures(self, track: _Track, now: float) -> None:
        if len(track.pose) < 3:
            return
        data = np.array(track.pose)
        times, yaw, pitch = data[:, 0], data[:, 1], data[:, 2]
        recent = times >= now - MOVE_WINDOW_S
        yaw_range, pitch_range = float(np.ptp(yaw[recent])), float(np.ptp(pitch[recent]))
        nod = back_and_forth(times, pitch, now, NOD_DEG)
        shake = back_and_forth(times, yaw, now, SHAKE_DEG, two_sided=True, window_s=SHAKE_WINDOW_S)
        if not shake and reversals(yaw, 2 * SHAKE_SIDE_DEG) >= 2 and float(np.ptp(yaw)) <= 2 * MAX_GESTURE_DEG:
            shake = float(np.ptp(yaw))  # непрерывная серия «нет-нет»
        if nod and yaw_range <= max(CALM_AXIS_DEG, 0.6 * pitch_range):
            track.last_nod = now
            track.nod_score = min(1.0, nod / 12.0)
        if shake and float(np.ptp(pitch)) <= max(CALM_AXIS_DEG, 0.6 * float(np.ptp(yaw))):
            track.last_shake = now
            track.shake_score = min(1.0, shake / 24.0)

    def _speech(
        self, track: _Track, mesh: FaceMesh, now: float, mic_on: bool | None
    ) -> tuple[Speech | None, float | None]:
        shape = mouth_shape(mesh.points)
        if shape is not None:
            track.mouth.append((now, *shape))
        while track.mouth and now - track.mouth[0][0] > SPEECH_WINDOW_S:
            track.mouth.popleft()
        if len(track.mouth) < 3 or now - track.mouth[0][0] < SPEECH_WINDOW_S / 2:
            return None, None
        data = np.array(track.mouth)
        activity = min(1.0, (oscillation(data[:, 1]) + 0.5 * oscillation(data[:, 2])) / SPEECH_FULL)
        if track.yawn_started is not None or now - track.last_yawn < SPEECH_WINDOW_S:
            activity = 0.0  # зевок – одно большое открывание рта, не речь
        if activity >= SPEECH_ON or (track.talking and activity >= SPEECH_OFF):
            track.talking, track.last_talk = True, now
        else:
            track.talking = False
        if now - track.last_talk > SPEECH_HOLD_S:
            return "silent", round(activity, 3)
        return ("side_talk" if mic_on is False else "speaking"), round(activity, 3)

    def _yawn(self, track: _Track, jaw_open: float, now: float) -> None:
        if jaw_open >= YAWN_JAW:
            if track.yawn_started is None:
                track.yawn_started = now
        else:
            if track.yawn_started is not None and now - track.yawn_started >= YAWN_MIN_S:
                track.yawns.append(now)
                track.last_yawn = now
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
