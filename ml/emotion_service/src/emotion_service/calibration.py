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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from emotion_service.labels import LABELS

NEUTRAL_TARGET = 0.6
CalibrationState = Literal["none", "collecting", "ready"]


def neutral_target(labels: tuple[str, ...] = LABELS) -> np.ndarray:
    q = np.full(len(labels), (1 - NEUTRAL_TARGET) / (len(labels) - 1))
    q[labels.index("neutral")] = NEUTRAL_TARGET
    return q


@dataclass
class _Person:
    started: float | None = None
    samples: list[np.ndarray] = field(default_factory=list)
    shift: np.ndarray | None = None  # base − log q


@dataclass(frozen=True, slots=True)
class CalibrationStatus:
    state: CalibrationState
    progress: float  # 0..1 во время сбора


class NeutralCalibrator:
    def __init__(self, duration_s: float = 3.0, strength: float = 1.0, min_samples: int = 5) -> None:
        self.duration_s = duration_s
        self.strength = strength
        self.min_samples = min_samples
        self._log_target = np.log(neutral_target())
        self._people: dict[str, _Person] = {}

    def start(self, key: str) -> None:
        """Начать сбор нейтрального лица; прежняя калибровка сбрасывается."""
        self._people[key] = _Person()

    def reset(self, key: str) -> None:
        self._people.pop(key, None)

    def status(self, key: str, now: float) -> CalibrationStatus:
        person = self._people.get(key)
        if person is None:
            return CalibrationStatus("none", 0.0)
        if person.shift is not None:
            return CalibrationStatus("ready", 1.0)
        elapsed = 0.0 if person.started is None else now - person.started
        return CalibrationStatus("collecting", min(1.0, elapsed / self.duration_s))

    def apply(self, key: str, probs: np.ndarray, now: float) -> tuple[np.ndarray, bool]:
        """Поправленные вероятности и признак «калибровка только что завершена» (для сброса сглаживания)."""
        person = self._people.get(key)
        if person is None:
            return probs, False
        log = np.log(np.clip(probs, 1e-6, 1.0))
        if person.shift is None:
            if person.started is None:
                person.started = now
            person.samples.append(log)
            if now - person.started < self.duration_s or len(person.samples) < self.min_samples:
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
