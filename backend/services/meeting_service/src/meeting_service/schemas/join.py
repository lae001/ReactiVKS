"""Схемы входа во встречу: ``/meetings/{id}/join``, ``/join/{invite_code}``, ``/participants/me/rejoin``."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from meeting_service.domain.consent import ConsentNotice
from meeting_service.domain.meetings import Meeting
from meeting_service.domain.participants import MAX_DISPLAY_NAME_LENGTH, Participant
from meeting_service.schemas.meetings import MeetingStatusValue

__all__ = [
    "ConsentNoticeResponse",
    "GuestJoinRequest",
    "GuestJoinResponse",
    "JoinInfoResponse",
    "JoinResultResponse",
    "OrganizerJoinRequest",
]

ConsentDecisionValue = Literal["granted", "denied"]


class OrganizerJoinRequest(BaseModel):
    consent: ConsentDecisionValue | None = Field(default=None, description="Обязательно, если анализ включен")


class GuestJoinRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH, examples=["Анна"])
    consent: ConsentDecisionValue | None = Field(default=None, description="Обязательно, если анализ включен")
    notice_version: str | None = Field(
        default=None,
        max_length=32,
        description="Версия показанного уведомления; обязательна, если анализ включен",
    )


class ConsentNoticeResponse(BaseModel):
    version: str
    text_md: str


class JoinInfoResponse(BaseModel):
    """Лобби гостя: что за встреча и, если анализ включен, текст уведомления о нем."""

    title: str
    organizer_name: str
    status: MeetingStatusValue
    scheduled_at: datetime | None
    analysis_enabled: bool
    consent_notice: ConsentNoticeResponse | None

    @classmethod
    def from_domain(cls, meeting: Meeting, notice: ConsentNotice | None) -> JoinInfoResponse:
        return cls(
            title=meeting.title,
            organizer_name=meeting.owner_name,
            status=meeting.status.value,
            scheduled_at=meeting.scheduled_at,
            analysis_enabled=meeting.analysis_enabled,
            consent_notice=ConsentNoticeResponse(version=notice.version, text_md=notice.text_md) if notice else None,
        )


class JoinedMeeting(BaseModel):
    id: UUID
    title: str
    status: MeetingStatusValue
    analysis_enabled: bool

    @classmethod
    def from_domain(cls, meeting: Meeting) -> JoinedMeeting:
        return cls(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status.value,
            analysis_enabled=meeting.analysis_enabled,
        )


class JoinResultResponse(BaseModel):
    """``JoinResult`` контракта: с этим клиент подключается к комнате LiveKit."""

    participant_id: UUID
    livekit_url: str = Field(examples=["wss://livekit.example.ru"])
    livekit_token: str
    meeting: JoinedMeeting

    @classmethod
    def from_domain(
        cls, meeting: Meeting, participant: Participant, *, livekit_url: str, livekit_token: str
    ) -> JoinResultResponse:
        return cls(
            participant_id=participant.id,
            livekit_url=livekit_url,
            livekit_token=livekit_token,
            meeting=JoinedMeeting.from_domain(meeting),
        )


class GuestJoinResponse(JoinResultResponse):
    """Вход гостя: дополнительно токен участника для ``Authorization: Participant <токен>``."""

    participant_token: str = Field(examples=["pt_…"])

    @classmethod
    def for_guest(
        cls,
        meeting: Meeting,
        participant: Participant,
        *,
        livekit_url: str,
        livekit_token: str,
        participant_token: str,
    ) -> GuestJoinResponse:
        return cls(
            participant_id=participant.id,
            participant_token=participant_token,
            livekit_url=livekit_url,
            livekit_token=livekit_token,
            meeting=JoinedMeeting.from_domain(meeting),
        )
