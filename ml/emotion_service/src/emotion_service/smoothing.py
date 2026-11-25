"""Сглаживание во времени: экспоненциальное среднее вероятностей по участнику (α = 0,4).

Без сглаживания доминирующая эмоция «мигает» между соседними кадрами; EMA с α = 0,4 при 3 кадрах/с дает
постоянную времени около секунды – резкая смена выражения видна организатору за 1–2 такта.
"""

from __future__ import annotations

import numpy as np


class TemporalSmoother:
    def __init__(self, alpha: float = 0.4, reset_after_s: float = 3.0) -> None:
        if not 0 < alpha <= 1:
            raise ValueError("alpha должна быть в (0, 1]")
        self.alpha = alpha
        self.reset_after_s = reset_after_s
        self._state: dict[str, tuple[np.ndarray, float]] = {}

    def update(self, key: str, probs: np.ndarray, now: float) -> np.ndarray:
        previous = self._state.get(key)
        if previous is None or now - previous[1] > self.reset_after_s:
            smoothed = probs.astype(np.float64)
        else:
            smoothed = self.alpha * probs + (1 - self.alpha) * previous[0]
        self._state[key] = (smoothed, now)
        return smoothed

    def touch_missing(self, key: str, now: float) -> None:
        """Лицо не найдено: состояние сбрасывается, если лица нет дольше reset_after_s."""
        previous = self._state.get(key)
        if previous is not None and now - previous[1] > self.reset_after_s:
            del self._state[key]

    def reset(self, key: str) -> None:
        self._state.pop(key, None)
