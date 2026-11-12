"""Ответы внутреннего API встреч."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from meeting_service.schemas.meetings import MeetingResponse, MeetingStatusValue
from meeting_service.schemas.participants import ParticipantResponse


class MeetingAccessResponse(BaseModel):
    allowed: bool
    meeting_status: MeetingStatusValue | None = None
    analysis_enabled: bool | None = None


class ParticipantSnapshotResponse(ParticipantResponse):
    updated_at: datetime
    last_joined_at: datetime | None


class MeetingSnapshotResponse(MeetingResponse):
    owner_id: UUID
    participants: list[ParticipantSnapshotResponse]
