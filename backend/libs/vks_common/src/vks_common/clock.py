"""Часы, подменяемые в тестах.

Сценарии получают время от :class:`Clock`, а не вызывают ``datetime.now()``: иначе правило «токен истек» нельзя
проверить детерминированно. Домен время не запрашивает вовсе – получает его аргументом.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

__all__ = ["Clock", "FixedClock", "SystemClock"]


class Clock(Protocol):
    """Источник текущего момента."""

    def now(self) -> datetime:
        """Текущий момент в UTC."""
        ...


class SystemClock:
    """Настоящие часы."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Часы, которые стоят, пока их не передвинут. Для тестов."""

    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("момент должен быть с часовым поясом")
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def advance(self, delta: timedelta) -> None:
        """Передвинуть часы вперед (или назад при отрицательном ``delta``)."""
        self._moment += delta
