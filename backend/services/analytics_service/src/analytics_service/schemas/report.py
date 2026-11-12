"""Контракт отчета и его ключевых моментов."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

DISCLAIMER = "Результаты отражают внешнее выражение лица и носят рекомендательный характер."


class ReportMeeting(BaseModel):
    title: str
    started_at: AwareDatetime | None
    ended_at: AwareDatetime | None
    duration_s: int | None


class OverallSummary(BaseModel):
    distribution: dict[str, float]
    face_detected_ratio: float
    negative_share: float
    mean_probabilities: dict[str, float]


class ParticipantSummary(BaseModel):
    participant_id: UUID
    display_name: str
    consent: Literal["granted", "denied", "revoked", "not_required"]
    distribution: dict[str, float] | None
    mean_probabilities: dict[str, float] | None
    dominant: str | None
    face_detected_ratio: float | None
    analyzed_seconds: int


class BackgroundPoint(BaseModel):
    ts: AwareDatetime
    valence: float


class ReportSummary(BaseModel):
    overall: OverallSummary
    participants: list[ParticipantSummary]
    participant_count: int
    consent_ratio: float
    emotional_background: list[BackgroundPoint]


class ReportMarker(BaseModel):
    id: UUID
    ts: AwareDatetime
    kind: Literal["auto_shift", "manual"]
    participant_id: UUID | None
    label: str
    details: dict[str, object]


class ReportResponse(BaseModel):
    meeting_id: UUID
    status: Literal["pending", "ready", "failed"]
    model_version: str | None
    meeting: ReportMeeting
    summary: ReportSummary | None = Field(default=None, exclude_if=lambda value: value is None)
    markers: list[ReportMarker]
    disclaimer: str = DISCLAIMER
