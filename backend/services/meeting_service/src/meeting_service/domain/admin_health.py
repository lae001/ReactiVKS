"""Состояние компонентов: данные без HTTP-схем."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

HealthState = Literal["ok", "degraded", "down"]


@dataclass(slots=True)
class ComponentStatus:
    status: HealthState
    rooms: int | None = None
    participants: int | None = None
    last_heartbeat: datetime | None = None


@dataclass(slots=True)
class HealthSnapshot:
    status: HealthState
    checked_at: datetime
    components: dict[str, ComponentStatus]
