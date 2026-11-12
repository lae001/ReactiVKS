"""Контракт временных рядов."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from analytics_service.domain.series import Resolution


class SeriesPoint(BaseModel):
    ts: AwareDatetime
    p: tuple[float, ...] | None
    face_ratio: float


class ParticipantSeries(BaseModel):
    participant_id: UUID
    points: list[SeriesPoint]


class SeriesResponse(BaseModel):
    resolution: Resolution
    labels: tuple[str, ...]
    series: list[ParticipantSeries]
