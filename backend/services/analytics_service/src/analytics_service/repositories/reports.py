"""Очередь отчетов и выдача сохраненной сводки."""

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Update, insert, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.domain.report import Marker, ReportContent, ReportParticipant
from analytics_service.domain.report_jobs import ReportJob, ReportView, SampleWatermark
from analytics_service.domain.series import Bucket
from analytics_service.models import PROBABILITIES, markers, meetings, participants, reports, sample_offsets, series


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, meeting_id: UUID, at: datetime) -> None:
        await self.session.execute(
            pg_insert(reports)
            .from_select(
                ["meeting_id", "updated_at"],
                select(meetings.c.meeting_id, literal(at, type_=reports.c.updated_at.type)).where(
                    meetings.c.meeting_id == meeting_id, meetings.c.status == "ended"
                ),
            )
            .on_conflict_do_nothing()
        )

    async def due(self, now: datetime) -> list[tuple[UUID, bool]]:
        rows = await self.session.execute(
            select(reports.c.meeting_id, reports.c.target_offset, reports.c.updated_at, meetings.c.ended_at)
            .join(meetings, meetings.c.meeting_id == reports.c.meeting_id)
            .where(
                reports.c.status == "pending",
                meetings.c.ended_at <= now - timedelta(seconds=5),
                reports.c.updated_at <= now - timedelta(seconds=5),
                or_(reports.c.locked_until.is_(None), reports.c.locked_until <= now),
            )
            .order_by(reports.c.updated_at)
            .limit(32)
        )
        return [
            (
                row.meeting_id,
                row.target_offset is None and max(row.ended_at, row.updated_at) > now - timedelta(seconds=60),
            )
            for row in rows
        ]

    async def reserve(self, meeting_id: UUID, now: datetime, target: SampleWatermark | None) -> ReportJob | None:
        meeting = (
            (await self.session.execute(select(meetings).where(meetings.c.meeting_id == meeting_id).with_for_update()))
            .mappings()
            .one_or_none()
        )
        if meeting is None or meeting.ended_at is None:
            return None
        row = (await self.session.execute(select(reports).where(reports.c.meeting_id == meeting_id))).mappings().one()
        if row.status != "pending" or (row.locked_until is not None and row.locked_until > now):
            return None
        if row.sealed_at is None:
            if row.target_offset is not None:
                target = (row.target_partition, row.target_offset)
            elif target is not None:
                await self.session.execute(
                    update(reports)
                    .where(reports.c.meeting_id == meeting_id)
                    .values(target_partition=target[0], target_offset=target[1])
                )
            if now < max(meeting.ended_at, row.updated_at) + timedelta(seconds=60) and not await self._caught_up(
                target
            ):
                return None

        attempt = row.attempts + 1
        await self.session.execute(
            update(reports)
            .where(reports.c.meeting_id == meeting_id)
            .values(attempts=attempt, locked_until=now + timedelta(seconds=30), sealed_at=row.sealed_at or now)
        )
        members = await self.session.execute(
            select(participants).where(participants.c.meeting_id == meeting_id).order_by(participants.c.participant_id)
        )
        data = await self.session.execute(
            select(series).where(series.c.meeting_id == meeting_id).order_by(series.c.ts, series.c.participant_id)
        )
        return ReportJob(
            meeting_id,
            meeting.owner_id,
            attempt,
            [ReportParticipant(member.participant_id, member.display_name, member.consent_state) for member in members],
            [
                Bucket(
                    point.meeting_id,
                    point.participant_id,
                    point.ts,
                    point.samples,
                    point.face_samples,
                    tuple(point._mapping[label] for label in PROBABILITIES) if point.face_samples else None,
                    point.model_version,
                )
                for point in data
            ],
        )

    async def finish(
        self,
        job: ReportJob,
        now: datetime,
        content: ReportContent,
        *,
        marker_ids: list[UUID],
    ) -> bool:
        result = await self.session.scalar(
            self._current_attempt(job)
            .values(
                status="ready",
                summary=content.summary,
                model_version=content.model_version,
                generated_at=now,
                updated_at=now,
                locked_until=None,
            )
            .returning(reports.c.meeting_id)
        )
        if result is None:
            return False
        if content.markers:
            await self.session.execute(
                insert(markers),
                [
                    _marker_row(job.meeting_id, marker_id, marker)
                    for marker_id, marker in zip(marker_ids, content.markers, strict=True)
                ],
            )
        return True

    async def fail(self, job: ReportJob, now: datetime, *, terminal: bool) -> bool:
        result = await self.session.scalar(
            self._current_attempt(job)
            .values(
                status="failed" if terminal else "pending",
                error="report_build_failed",
                updated_at=now,
                locked_until=None if terminal else now + timedelta(seconds=5),
            )
            .returning(reports.c.meeting_id)
        )
        return result is not None

    async def read(self, meeting_id: UUID, owner_id: UUID) -> ReportView | None:
        row = (
            (
                await self.session.execute(
                    select(
                        meetings.c.title,
                        meetings.c.started_at,
                        meetings.c.ended_at,
                        reports.c.status,
                        reports.c.summary,
                        reports.c.model_version,
                    )
                    .outerjoin(reports, reports.c.meeting_id == meetings.c.meeting_id)
                    .where(meetings.c.meeting_id == meeting_id, meetings.c.owner_id == owner_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        marks = await self.session.execute(
            select(
                markers.c.id, markers.c.ts, markers.c.kind, markers.c.participant_id, markers.c.label, markers.c.details
            )
            .where(markers.c.meeting_id == meeting_id)
            .order_by(markers.c.ts, markers.c.id)
        )
        return ReportView(
            row.title,
            row.started_at,
            row.ended_at,
            row.status or "pending",
            row.model_version,
            row.summary,
            [dict(marker) for marker in marks.mappings()],
        )

    def _current_attempt(self, job: ReportJob) -> Update:
        return update(reports).where(
            reports.c.meeting_id == job.meeting_id, reports.c.status == "pending", reports.c.attempts == job.attempt
        )

    async def _caught_up(self, target: SampleWatermark | None) -> bool:
        if target is None:
            return False
        partition, end = target
        offset = await self.session.scalar(
            select(sample_offsets.c.next_offset).where(sample_offsets.c.partition == partition)
        )
        return (cast(int | None, offset) or 0) >= end


def _marker_row(meeting_id: UUID, marker_id: UUID, marker: Marker) -> dict[str, object]:
    return {
        "id": marker_id,
        "meeting_id": meeting_id,
        "ts": marker.ts,
        "kind": "auto_shift",
        "participant_id": marker.participant_id,
        "label": marker.label,
        "details": marker.details,
    }
