"""Построение и чтение отчета."""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.domain.report import build_report
from analytics_service.domain.report_jobs import ReadWatermark, ReportJob, ReportView
from analytics_service.repositories.outbox import ReportOutbox
from analytics_service.repositories.reports import ReportRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.errors import NotFound
from vks_common.ids import new_id
from vks_common.logging import get_logger
from vks_contracts.ml_events import EMOTIONS
from vks_contracts.report_events import ReportFailed, ReportReady

_logger = get_logger(__name__)


class BuildReports:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        watermark: ReadWatermark,
        *,
        shift_threshold: float,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._watermark = watermark
        self._threshold = shift_threshold

    async def execute(self) -> None:
        async with self._sessions() as session, transaction(session):
            due = await ReportRepository(session).due(self._clock.now())
        for meeting_id, needs_watermark in due:
            target = await self._watermark(meeting_id) if needs_watermark else None
            async with self._sessions() as session, transaction(session):
                job = await ReportRepository(session).reserve(meeting_id, self._clock.now(), target)
            if job is not None:
                await self._build(job)

    async def _build(self, job: ReportJob) -> None:
        if job.attempt > 3:
            await self._fail(job)
            return
        try:
            content = await asyncio.to_thread(build_report, job.participants, job.buckets, EMOTIONS, self._threshold)
        except Exception:  # noqa: BLE001 - граница вычисления отчета: повтор или report.failed.
            _logger.exception("report computation failed", meeting_id=str(job.meeting_id))
            await self._fail(job)
            return
        now = self._clock.now()
        async with self._sessions() as session, transaction(session):
            if await ReportRepository(session).finish(
                job, now, content, marker_ids=[new_id() for _ in content.markers]
            ):
                await ReportOutbox(session).add(ReportReady(meeting_id=job.meeting_id, owner_id=job.owner_id), now)

    async def _fail(self, job: ReportJob) -> None:
        now = self._clock.now()
        terminal = job.attempt >= 3
        async with self._sessions() as session, transaction(session):
            if await ReportRepository(session).fail(job, now, terminal=terminal) and terminal:
                event = ReportFailed(meeting_id=job.meeting_id, owner_id=job.owner_id, reason="report_build_failed")
                await ReportOutbox(session).add(event, now)


class ReadReport:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(self, meeting_id: UUID, owner_id: UUID) -> ReportView:
        async with transaction(self._session):
            report = await ReportRepository(self._session).read(meeting_id, owner_id)
            if report is None:
                raise NotFound()
            return report
