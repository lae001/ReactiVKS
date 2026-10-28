"""Топик ``meeting.events`` – производитель meeting-service (через outbox), ключ – ``meeting_id``."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from vks_contracts.envelope import MeetingKeyed
from vks_contracts.topics import Topic

__all__ = [
    "ConsentChanged",
    "ConsentState",
    "MeetingCancelled",
    "MeetingCreated",
    "MeetingDeleted",
    "MeetingEnded",
    "MeetingStarted",
    "MeetingUpdated",
    "ParticipantJoined",
    "ParticipantLeft",
    "ParticipantRegistered",
]

ConsentState = Literal["granted", "denied", "revoked", "not_required"]


class _MeetingEvent(MeetingKeyed):
    topic = Topic.MEETING_EVENTS


class MeetingCreated(_MeetingEvent):
    event_type = "meeting.created"

    owner_id: UUID
    title: str
    scheduled_at: AwareDatetime | None
    analysis_enabled: bool


class MeetingUpdated(_MeetingEvent):
    event_type = "meeting.updated"

    title: str
    scheduled_at: AwareDatetime | None
    analysis_enabled: bool


class MeetingStarted(_MeetingEvent):
    event_type = "meeting.started"

    owner_id: UUID
    title: str
    started_at: AwareDatetime
    analysis_enabled: bool
    analysis_fps: int = Field(ge=2, le=5)


class MeetingEnded(_MeetingEvent):
    event_type = "meeting.ended"

    ended_at: AwareDatetime
    reason: Literal["organizer", "empty_timeout", "admin"]


class MeetingCancelled(_MeetingEvent):
    event_type = "meeting.cancelled"


class MeetingDeleted(_MeetingEvent):
    """Потребители удаляют свои данные встречи."""

    event_type = "meeting.deleted"


class ParticipantRegistered(_MeetingEvent):
    event_type = "participant.registered"

    participant_id: UUID
    display_name: str
    role: Literal["organizer", "guest"]
    consent_state: ConsentState


class ParticipantJoined(_MeetingEvent):
    event_type = "participant.joined"

    participant_id: UUID
    joined_at: AwareDatetime


class ParticipantLeft(_MeetingEvent):
    event_type = "participant.left"

    participant_id: UUID
    left_at: AwareDatetime
    reason: Literal["left", "removed", "disconnected"]


class ConsentChanged(_MeetingEvent):
    event_type = "consent.changed"

    participant_id: UUID
    consent_state: ConsentState
    notice_version: str
    decided_at: AwareDatetime
