"""Доменные изменения → payload событий ``meeting.events`` (docs/api/events.md)."""

from __future__ import annotations

from datetime import datetime

from meeting_service.domain.meetings import Meeting
from meeting_service.domain.participants import Participant
from vks_contracts.meeting_events import (
    ConsentChanged,
    MeetingCreated,
    MeetingEnded,
    MeetingStarted,
    ParticipantRegistered,
)

__all__ = ["consent_changed", "meeting_created", "meeting_ended", "meeting_started", "participant_registered"]


def meeting_created(meeting: Meeting) -> MeetingCreated:
    return MeetingCreated(
        meeting_id=meeting.id,
        owner_id=meeting.owner_id,
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


def participant_registered(participant: Participant) -> ParticipantRegistered:
    return ParticipantRegistered(
        meeting_id=participant.meeting_id,
        participant_id=participant.id,
        display_name=participant.display_name,
        role=participant.role.value,
        consent_state=participant.consent_state.value,
    )


def consent_changed(participant: Participant, *, notice_version: str, decided_at: datetime) -> ConsentChanged:
    return ConsentChanged(
        meeting_id=participant.meeting_id,
        participant_id=participant.id,
        consent_state=participant.consent_state.value,
        notice_version=notice_version,
        decided_at=decided_at,
    )
