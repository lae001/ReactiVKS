"""Схемы эндпоинтов ``/api/v1/meetings``."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from meeting_service.domain.meetings import (
    MAX_ANALYSIS_FPS,
    MAX_TITLE_LENGTH,
    MIN_ANALYSIS_FPS,
    UNCHANGED,
    MeetingEdit,
    MeetingOverview,
)

__all__ = [
    "CreateMeetingRequest",
    "MeetingPageResponse",
    "MeetingResponse",
    "MeetingStatusValue",
    "UpdateMeetingRequest",
]

MeetingStatusValue = Literal["scheduled", "active", "ended", "cancelled"]


class CreateMeetingRequest(BaseModel):
    """Не указанные ``analysis_enabled`` и ``analysis_fps`` берутся из настроек организатора."""

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH, examples=["Переговоры с ООО «Ромашка»"])
    scheduled_at: AwareDatetime | None = Field(default=None, description="null – встреча «сейчас»")
    analysis_enabled: bool | None = None
    analysis_fps: int | None = Field(default=None, ge=MIN_ANALYSIS_FPS, le=MAX_ANALYSIS_FPS)


class UpdateMeetingRequest(BaseModel):
    """Частичное изменение: не переданное поле не меняется. ``scheduled_at: null`` – перенести встречу на «сейчас».

    Время и параметры анализа меняются только до начала встречи (``409 meeting_not_editable``).
    """

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    scheduled_at: AwareDatetime | None = None
    analysis_enabled: bool | None = None
    analysis_fps: int | None = Field(default=None, ge=MIN_ANALYSIS_FPS, le=MAX_ANALYSIS_FPS)

    def to_domain(self) -> MeetingEdit:
        return MeetingEdit(
            title=self.title,
            # Явный null отличается от отсутствующего поля только по списку переданных полей.
            scheduled_at=self.scheduled_at if "scheduled_at" in self.model_fields_set else UNCHANGED,
            analysis_enabled=self.analysis_enabled,
            analysis_fps=self.analysis_fps,
        )


class MeetingResponse(BaseModel):
    """``Meeting`` контракта."""

    id: UUID
    title: str
    status: MeetingStatusValue
    invite_code: str = Field(examples=["k3m7qx4tpa"])
    invite_url: str = Field(examples=["https://vks.example.ru/j/k3m7qx4tpa"])
    analysis_enabled: bool
    analysis_fps: int
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    participants_count: int
    created_at: datetime

    @classmethod
    def from_domain(cls, overview: MeetingOverview, *, invite_url: str) -> MeetingResponse:
        meeting = overview.meeting
        return cls(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status.value,
            invite_code=meeting.invite_code,
            invite_url=invite_url,
            analysis_enabled=meeting.analysis_enabled,
            analysis_fps=meeting.analysis_fps,
            scheduled_at=meeting.scheduled_at,
            started_at=meeting.started_at,
            ended_at=meeting.ended_at,
            participants_count=overview.participants_count,
            created_at=meeting.created_at,
        )


class MeetingPageResponse(BaseModel):
    items: list[MeetingResponse]
    next_cursor: str | None = Field(description="Передать в `cursor`, чтобы получить следующую страницу")
