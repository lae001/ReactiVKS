"""Доменные изменения → payload событий ``meeting.events`` (docs/api/events.md)."""

from __future__ import annotations

from datetime import datetime

from meeting_service.domain.livekit import LeaveReason
from meeting_service.domain.meetings import Meeting, MeetingStatus
from meeting_service.domain.participants import Participant
from vks_contracts.meeting_events import (
    ConsentChanged,
    MeetingCancelled,
    MeetingCreated,
    MeetingDeleted,
    MeetingEnded,
    MeetingStarted,
    MeetingUpdated,
    ParticipantJoined,
    ParticipantLeft,
    ParticipantRegistered,
)

__all__ = [
    "consent_changed",
    "meeting_cancelled",
    "meeting_closed",
    "meeting_created",
    "meeting_deleted",
    "meeting_ended",
    "meeting_started",
    "meeting_updated",
    "participant_joined",
    "participant_left",
    "participant_registered",
]


def meeting_created(meeting: Meeting) -> MeetingCreated:
    return MeetingCreated(
        meeting_id=meeting.id,
        owner_id=meeting.owner_id,
        title=meeting.title,
        scheduled_at=meeting.scheduled_at,
        analysis_enabled=meeting.analysis_enabled,
    )


def meeting_updated(meeting: Meeting) -> MeetingUpdated:
    return MeetingUpdated(
        meeting_id=meeting.id,
        title=meeting.title,
        scheduled_at=meeting.scheduled_at,
        analysis_enabled=meeting.analysis_enabled,
    )


def meeting_started(meeting: Meeting) -> MeetingStarted:
    if meeting.started_at is None:  # pragma: no cover - started() всегда выставляет время
        raise ValueError("начатая встреча без started_at")
    return MeetingStarted(
        meeting_id=meeting.id,
        owner_id=meeting.owner_id,
        title=meeting.title,
        started_at=meeting.started_at,
        analysis_enabled=meeting.analysis_enabled,
        analysis_fps=meeting.analysis_fps,
    )


def meeting_ended(meeting: Meeting) -> MeetingEnded:
    if meeting.ended_at is None or meeting.end_reason is None:  # pragma: no cover - ended() выставляет оба
        raise ValueError("завершенная встреча без ended_at или end_reason")
    return MeetingEnded(meeting_id=meeting.id, ended_at=meeting.ended_at, reason=meeting.end_reason.value)


def meeting_cancelled(meeting: Meeting) -> MeetingCancelled:
    return MeetingCancelled(meeting_id=meeting.id)


def meeting_closed(meeting: Meeting) -> MeetingEnded | MeetingCancelled:
    """Событие закрытия встречи перед удалением (``Meeting.closed``): завершение или отмена."""
    if meeting.status is MeetingStatus.CANCELLED:
        return meeting_cancelled(meeting)
    return meeting_ended(meeting)


def meeting_deleted(meeting: Meeting) -> MeetingDeleted:
    return MeetingDeleted(meeting_id=meeting.id)


def participant_registered(participant: Participant) -> ParticipantRegistered:
    return ParticipantRegistered(
        meeting_id=participant.meeting_id,
        participant_id=participant.id,
        display_name=participant.display_name,
        role=participant.role.value,
        consent_state=participant.consent_state.value,
    )


def participant_joined(participant: Participant, *, joined_at: datetime) -> ParticipantJoined:
    return ParticipantJoined(meeting_id=participant.meeting_id, participant_id=participant.id, joined_at=joined_at)


def participant_left(participant: Participant, *, left_at: datetime, reason: LeaveReason) -> ParticipantLeft:
    return ParticipantLeft(
        meeting_id=participant.meeting_id, participant_id=participant.id, left_at=left_at, reason=reason.value
    )


def consent_changed(participant: Participant, *, notice_version: str, decided_at: datetime) -> ConsentChanged:
    return ConsentChanged(
        meeting_id=participant.meeting_id,
        participant_id=participant.id,
        consent_state=participant.consent_state.value,
        notice_version=notice_version,
        decided_at=decided_at,
    )
