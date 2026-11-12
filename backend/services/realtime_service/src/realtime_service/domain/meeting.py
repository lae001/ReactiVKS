"""Данные встречи, необходимые для подписки."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

ParticipantRole = Literal["organizer", "guest"]


@dataclass(frozen=True, slots=True)
class ParticipantSnapshot:
    id: UUID
    display_name: str
    role: ParticipantRole
    has_consent: bool
    is_online: bool
    is_removed: bool
    updated_at: datetime
    presence_at: datetime | None


@dataclass(frozen=True, slots=True)
class MeetingSnapshot:
    owner_id: UUID
    is_analyzed: bool
    is_closed: bool
    participants: tuple[ParticipantSnapshot, ...]


class MeetingReader(Protocol):
    async def is_allowed(self, meeting_id: UUID, user_id: UUID) -> bool: ...

    async def snapshot(self, meeting_id: UUID) -> MeetingSnapshot | None: ...
