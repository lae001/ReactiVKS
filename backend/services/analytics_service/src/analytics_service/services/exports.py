"""Экспорт и отметки владельца встречи."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.domain.report_jobs import ReportView
from analytics_service.repositories.exports import ExportRepository
from analytics_service.repositories.reports import ReportRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.errors import Conflict, NotFound, ValidationFailed
from vks_common.ids import new_id


class MeetingInProgress(Conflict):
    code = "meeting_in_progress"


class ReportNotReady(Conflict):
    code = "report_not_ready"


class ReportExports:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.repository = ExportRepository(session)

    async def csv_rows(self, meeting_id: UUID, owner_id: UUID) -> list[RowMapping]:
        async with transaction(self.session):
            meeting = await self.repository.meeting(meeting_id, owner_id)
            if meeting is None:
                raise NotFound()
            if meeting.status != "ended":
                raise MeetingInProgress()
            return await self.repository.rows(meeting_id)

    async def pdf_report(self, meeting_id: UUID, owner_id: UUID) -> ReportView:
        async with transaction(self.session):
            report = await ReportRepository(self.session).read(meeting_id, owner_id)
            if report is None:
                raise NotFound()
            if report.status != "ready":
                raise ReportNotReady()
            return report

    async def mark(
        self, meeting_id: UUID, owner_id: UUID, *, ts: datetime | None, label: str, participant_id: UUID | None
    ) -> RowMapping:
        async with transaction(self.session):
            meeting = await self.repository.meeting(meeting_id, owner_id)
            if meeting is None:
                raise NotFound()
            at = ts or self.clock.now()
            if meeting.started_at is None or at < meeting.started_at or at > (meeting.ended_at or self.clock.now()):
                raise ValidationFailed("Marker is outside the meeting interval", field="ts")
            if participant_id is not None and not await self.repository.participant(meeting_id, participant_id):
                raise ValidationFailed("Participant does not belong to the meeting", field="participant_id")
            return await self.repository.add_marker(meeting_id, owner_id, new_id(), at, label, participant_id)

    async def unmark(self, meeting_id: UUID, owner_id: UUID, marker_id: UUID) -> None:
        async with transaction(self.session):
            if await self.repository.meeting(meeting_id, owner_id) is None:
                raise NotFound()
            if not await self.repository.delete_marker(meeting_id, marker_id):
                raise NotFound()
