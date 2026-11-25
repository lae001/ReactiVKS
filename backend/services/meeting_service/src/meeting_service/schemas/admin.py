"""Сводка состояния и список встреч администратора."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from meeting_service.schemas.meetings import MeetingResponse

HealthState = Literal["ok", "degraded", "down"]


class AdminMeeting(MeetingResponse):
    owner_id: UUID
    online_participants: int


class AdminMeetingPage(BaseModel):
    items: list[AdminMeeting]
    next_cursor: str | None


class ComponentHealth(BaseModel):
    status: HealthState
    rooms: int | None = None
    participants: int | None = None
    last_heartbeat: datetime | None = None


class AdminHealth(BaseModel):
    status: HealthState
    checked_at: datetime
    components: dict[str, ComponentHealth]
