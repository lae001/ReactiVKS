"""Выборка кадров 2–5 кадров/с: «последний кадр выигрывает» и адаптивная частота тактов.

Дорожка участника приходит с частотой камеры (15–30 кадров/с). Читатель дорожки только перезаписывает последний
кадр участника, такт анализа забирает по одному кадру на участника. Очередь не накапливается, поэтому при
перегрузке растет не задержка, а снижается частота.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sample[T]:
    participant_id: str
    frame: T
    received_at: float  # time.monotonic() момента получения


class FrameSampler[T]:
    """Хранит только последний кадр каждого участника. Кадр хранится сырым: конвертация – только в такте."""

    def __init__(self) -> None:
        self._latest: dict[str, Sample[T]] = {}
        self._lock = threading.Lock()
        self.received = 0
        self.dropped = 0

    def put(self, participant_id: str, frame: T, received_at: float) -> None:
        with self._lock:
            self.received += 1
            if participant_id in self._latest:
                self.dropped += 1
            self._latest[participant_id] = Sample(participant_id, frame, received_at)

    def take(self) -> list[Sample[T]]:
        """Последние кадры, пришедшие после предыдущего такта; повторно один кадр не выдается."""
        with self._lock:
            samples = list(self._latest.values())
            self._latest.clear()
            return samples

    def remove(self, participant_id: str) -> None:
        with self._lock:
            self._latest.pop(participant_id, None)


class AdaptiveRate:
    """Адаптивная частота тактов (docs/ml/emotion-ml-service.md, «Конвейер обработки»).

    - такт дольше 80 % периода 5 раз подряд → частота −1 кадр/с, но не ниже min_fps;
    - перегрузка сохраняется на min_fps → degraded = True (ml.status degraded);
    - такт короче 50 % периода 10 раз подряд → частота +1 кадр/с, но не выше target_fps.
    """

    OVERLOAD_SHARE = 0.8
    SPARE_SHARE = 0.5
    OVERLOAD_TICKS = 5
    RECOVER_TICKS = 10

    def __init__(self, target_fps: float = 3.0, min_fps: float = 2.0, max_fps: float = 5.0) -> None:
        if not 0 < min_fps <= target_fps <= max_fps:
            raise ValueError("Требуется 0 < min_fps ≤ target_fps ≤ max_fps")
        self.target_fps = target_fps
        self.min_fps = min_fps
        self.fps = target_fps
        self.degraded = False
        self._overloaded = 0
        self._spare = 0

    @property
    def period(self) -> float:
        return 1.0 / self.fps

    def record(self, tick_seconds: float) -> float:
        if tick_seconds > self.OVERLOAD_SHARE * self.period:
            self._overloaded += 1
            self._spare = 0
            if self._overloaded >= self.OVERLOAD_TICKS:
                self._overloaded = 0
                if self.fps > self.min_fps:
                    self.fps = max(self.min_fps, self.fps - 1)
                else:
                    self.degraded = True
        elif tick_seconds < self.SPARE_SHARE * self.period:
            self._overloaded = 0
            self._spare += 1
            if self._spare >= self.RECOVER_TICKS:
                self._spare = 0
                self.degraded = False
                self.fps = min(self.target_fps, self.fps + 1)
        else:
            self._overloaded = 0
            self._spare = 0
        return self.fps
