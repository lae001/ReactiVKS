"""Схемы участников встречи: ``GET /meetings/{id}/participants`` и модерация."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from meeting_service.domain.participants import Participant

__all__ = ["MuteRequest", "ParticipantListResponse", "ParticipantResponse"]


class ParticipantResponse(BaseModel):
    """``Participant`` контракта. ``online`` – сейчас в комнате (по вебхукам LiveKit)."""

    id: UUID
    display_name: str
    role: Literal["organizer", "guest"]
    consent_state: Literal["granted", "denied", "revoked", "not_required"]
    online: bool
    is_removed: bool
    first_joined_at: datetime | None
    last_left_at: datetime | None

    @classmethod
    def from_domain(cls, participant: Participant) -> ParticipantResponse:
        return cls(
            id=participant.id,
            display_name=participant.display_name,
            role=participant.role.value,
            consent_state=participant.consent_state.value,
            online=participant.is_online,
            is_removed=participant.is_removed,
            first_joined_at=participant.first_joined_at,
            last_left_at=participant.last_left_at,
        )


class ParticipantListResponse(BaseModel):
    items: list[ParticipantResponse]


class MuteRequest(BaseModel):
    kind: Literal["audio", "video"]
