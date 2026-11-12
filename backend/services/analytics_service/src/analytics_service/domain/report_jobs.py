"""Состояние отложенной сборки отчета."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from analytics_service.domain.report import ReportParticipant
from analytics_service.domain.series import Bucket

type SampleWatermark = tuple[int, int]
type ReadWatermark = Callable[[UUID], Awaitable[SampleWatermark | None]]


@dataclass(frozen=True, slots=True)
class ReportJob:
    meeting_id: UUID
    owner_id: UUID
    attempt: int
    participants: list[ReportParticipant]
    buckets: list[Bucket]


@dataclass(frozen=True, slots=True)
class ReportView:
    title: str
    started_at: datetime | None
    ended_at: datetime | None
    status: Literal["pending", "ready", "failed"]
    model_version: str | None
    summary: dict[str, object] | None
    markers: list[dict[str, object]]
