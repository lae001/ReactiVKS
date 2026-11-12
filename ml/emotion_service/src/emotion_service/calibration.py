"""Калибровка под человека: эмоции относительно его собственного нейтрального лица.

Модель обучена на чужих лицах FER-2013. У конкретного человека «спокойное» выражение, свет от монитора и ракурс
камеры снизу смещают ответ модели – чаще всего в сторону sad: на тесте FER-2013 модель предсказывает sad с той же
частотой, что и разметка (17,3 % против 17,4 %), а у живого участника в покое – стабильно. Общая поправка классов
это не лечит (на тесте она снижает accuracy и macro-F1, experiments.md, §8), поэтому смещение снимается для
каждого человека отдельно.

Пока участник несколько секунд держит нейтральное лицо, копится среднее логарифмов вероятностей base. Дальше
log p' = log p − s · (base − log q), где q – целевое распределение нейтрального кадра (neutral = NEUTRAL_TARGET,
остальное поровну), s – сила поправки. Кадр, как при калибровке, дает ровно q; отклонение от личного нейтрального
выражения (улыбка, поднятые брови) сдвигает распределение к соответствующей эмоции.

Автокалибровка (auto): кнопку нажимать не нужно – копятся только «спокойные» кадры (is_calm: голова к камере,
нет улыбки, открытого рта, поднятых или сведенных бровей), и когда спокойных кадров набирается на auto_s секунд
(перерыв больше max_gap_s начинает сбор заново), калибровка готова. Кадры с эмоциями в базу не попадают, поэтому
улыбка в первые секунды встречи не станет «нейтральным» лицом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from emotion_service.labels import LABELS

NEUTRAL_TARGET = 0.6
CalibrationState = Literal["none", "collecting", "ready"]

# Спокойное лицо для автокалибровки: пороги коэффициентов MediaPipe (0–1) и позы головы.
CALM_MAX_BLENDSHAPE = {
    "mouthSmileLeft": 0.3,
    "mouthSmileRight": 0.3,
    "jawOpen": 0.2,
    "browInnerUp": 0.4,
    "browDownLeft": 0.4,
    "browDownRight": 0.4,
    "eyeWideLeft": 0.4,
    "eyeWideRight": 0.4,
    "mouthFrownLeft": 0.4,
    "mouthFrownRight": 0.4,
    "noseSneerLeft": 0.4,
    "noseSneerRight": 0.4,
}
CALM_MAX_POSE_DEG = 15.0


def is_calm(blendshapes: dict[str, float], yaw_deg: float, pitch_deg: float) -> bool:
    """Лицо спокойно и смотрит в камеру – кадр годится как личное нейтральное выражение."""
    if abs(yaw_deg) > CALM_MAX_POSE_DEG or abs(pitch_deg) > CALM_MAX_POSE_DEG:
        return False
    return all(blendshapes.get(name, 0.0) <= limit for name, limit in CALM_MAX_BLENDSHAPE.items())


def neutral_target(labels: tuple[str, ...] = LABELS) -> np.ndarray:
    q = np.full(len(labels), (1 - NEUTRAL_TARGET) / (len(labels) - 1))
    q[labels.index("neutral")] = NEUTRAL_TARGET
    return q


@dataclass
class _Person:
    started: float | None = None
    samples: list[np.ndarray] = field(default_factory=list)
    shift: np.ndarray | None = None  # base − log q
    auto: bool = False
    last_calm: float | None = None


@dataclass(frozen=True, slots=True)
class CalibrationStatus:
    state: CalibrationState
    progress: float  # 0..1 во время сбора
    auto: bool = False  # автокалибровка по спокойным кадрам (без кнопки)


class NeutralCalibrator:
    def __init__(
        self,
        duration_s: float = 3.0,
        strength: float = 1.0,
        min_samples: int = 5,
        auto: bool = False,
        auto_s: float = 5.0,
        max_gap_s: float = 1.5,
    ) -> None:
        self.duration_s = duration_s
        self.auto = auto  # новые участники калибруются автоматически
        self.auto_s = auto_s
        self.max_gap_s = max_gap_s
        self.strength = strength
        self.min_samples = min_samples
        self._log_target = np.log(neutral_target())
        self._people: dict[str, _Person] = {}

    def start(self, key: str, auto: bool = False) -> None:
        """Начать сбор нейтрального лица; прежняя калибровка сбрасывается. auto – копить только спокойные кадры."""
        self._people[key] = _Person(auto=auto)

    def reset(self, key: str) -> None:
        """Сбросить калибровку; при auto сбор начнется заново со следующего кадра."""
        self._people.pop(key, None)

    def status(self, key: str, now: float) -> CalibrationStatus:
        person = self._people.get(key)
        if person is None:
            return CalibrationStatus("none", 0.0)
        if person.shift is not None:
            return CalibrationStatus("ready", 1.0, person.auto)
        if person.started is None:
            return CalibrationStatus("collecting", 0.0, person.auto)
        elapsed = (person.last_calm if person.auto and person.last_calm is not None else now) - person.started
        need = self.auto_s if person.auto else self.duration_s
        return CalibrationStatus("collecting", min(1.0, elapsed / need), person.auto)

    def apply(self, key: str, probs: np.ndarray, now: float, calm: bool = True) -> tuple[np.ndarray, bool]:
        """Поправленные вероятности и признак «калибровка только что завершена» (для сброса сглаживания).

        calm – кадр спокойный (is_calm); учитывается только автокалибровкой, ручная полагается на участника."""
        person = self._people.get(key)
        if person is None:
            if not self.auto:
                return probs, False
            person = self._people[key] = _Person(auto=True)
        log = np.log(np.clip(probs, 1e-6, 1.0))
        if person.shift is None:
            if person.auto:
                gap = person.last_calm is not None and now - person.last_calm > self.max_gap_s
                if gap:  # спокойствие прервалось надолго – сбор заново
                    person.samples.clear()
                    person.started = person.last_calm = None
                if not calm:
                    return probs, False
                person.last_calm = now
            if person.started is None:
                person.started = now
            person.samples.append(log)
            need = self.auto_s if person.auto else self.duration_s
            if now - person.started < need or len(person.samples) < self.min_samples:
                return probs, False
            person.shift = np.mean(person.samples, axis=0) - self._log_target
            person.samples.clear()
            return self._correct(log, person.shift), True
        return self._correct(log, person.shift), False

    def _correct(self, log: np.ndarray, shift: np.ndarray) -> np.ndarray:
        adjusted = log - self.strength * shift
        adjusted -= adjusted.max()
        exp = np.exp(adjusted)
        result: np.ndarray = exp / exp.sum()
        return result
