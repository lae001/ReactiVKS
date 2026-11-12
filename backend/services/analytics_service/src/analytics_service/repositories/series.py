"""Хранение посекундных агрегатов и непрерывной границы Kafka."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import RowMapping, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.domain.series import PROBABILITY_COUNT, RESOLUTION_SECONDS, Bucket, Point, Resolution
from analytics_service.models import (
    PROBABILITIES,
    consent_history,
    deleted_meetings,
    meetings,
    participants,
    sample_offsets,
    series,
)


class SeriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_offset(self, partition: int, initial: int) -> int:
        await self.session.execute(
            insert(sample_offsets).values(partition=partition, next_offset=initial).on_conflict_do_nothing()
        )
        value = await self.session.scalar(
            select(sample_offsets.c.next_offset).where(sample_offsets.c.partition == partition).with_for_update()
        )
        return cast(int, value)

    async def save_offset(self, partition: int, offset: int) -> None:
        await self.session.execute(
            update(sample_offsets).where(sample_offsets.c.partition == partition).values(next_offset=offset)
        )

    async def lock_meetings(self, ids: set[UUID]) -> dict[UUID, RowMapping]:
        rows = await self.session.execute(
            select(meetings).where(meetings.c.meeting_id.in_(ids)).order_by(meetings.c.meeting_id).with_for_update()
        )
        return {row.meeting_id: row for row in rows.mappings()}

    async def deleted(self, ids: set[UUID]) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(deleted_meetings.c.meeting_id).where(deleted_meetings.c.meeting_id.in_(ids))
            )
        )

    async def read_consents(
        self, ids: set[UUID], earliest: datetime
    ) -> dict[UUID, tuple[UUID, list[tuple[datetime, bool]]]]:
        owners = await self.session.execute(
            select(participants.c.participant_id, participants.c.meeting_id).where(
                participants.c.participant_id.in_(ids)
            )
        )
        result: dict[UUID, tuple[UUID, list[tuple[datetime, bool]]]] = {
            row.participant_id: (row.meeting_id, []) for row in owners
        }
        history = consent_history.alias()
        previous = (
            select(func.max(history.c.decided_at))
            .where(history.c.participant_id == consent_history.c.participant_id, history.c.decided_at < earliest)
            .scalar_subquery()
        )
        rows = await self.session.execute(
            select(consent_history)
            .where(
                consent_history.c.participant_id.in_(ids),
                (consent_history.c.decided_at >= earliest) | (consent_history.c.decided_at == previous),
            )
            .order_by(consent_history.c.decided_at)
        )
        for row in rows:
            result[row.participant_id][1].append((row.decided_at, row.is_granted))
        return result

    async def write(self, buckets: Sequence[Bucket]) -> None:
        if not buckets:
            return
        rows = [
            {
                "meeting_id": bucket.meeting_id,
                "participant_id": bucket.participant_id,
                "ts": bucket.ts,
                "samples": bucket.samples,
                "face_samples": bucket.face_samples,
                "model_version": bucket.model_version,
                **dict(zip(PROBABILITIES, bucket.probabilities or (None,) * PROBABILITY_COUNT, strict=True)),
            }
            for bucket in buckets
        ]
        statement = insert(series)
        incoming = statement.excluded
        faces = series.c.face_samples + incoming.face_samples
        averages = {
            label: (
                func.coalesce(series.c[label], 0) * series.c.face_samples
                + func.coalesce(incoming[label], 0) * incoming.face_samples
            )
            / func.nullif(faces, 0)
            for label in PROBABILITIES
        }
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[series.c.meeting_id, series.c.participant_id, series.c.ts],
                set_={
                    "samples": series.c.samples + incoming.samples,
                    "face_samples": faces,
                    "model_version": incoming.model_version,
                    **averages,
                },
            ),
            rows,
        )

    async def read(
        self, meeting_id: UUID, *, resolution: Resolution, participant_id: UUID | None, since: datetime | None
    ) -> dict[UUID, list[Point]]:
        ts = func.date_bin(
            timedelta(seconds=RESOLUTION_SECONDS[resolution]), series.c.ts, datetime(1970, 1, 1, tzinfo=UTC)
        )
        faces = func.sum(series.c.face_samples)
        statement = (
            select(
                series.c.participant_id,
                ts.label("ts"),
                (faces * 1.0 / func.sum(series.c.samples)).label("face_ratio"),
                *(
                    (func.sum(series.c[label] * series.c.face_samples) / func.nullif(faces, 0)).label(label)
                    for label in PROBABILITIES
                ),
            )
            .where(series.c.meeting_id == meeting_id)
            .group_by(series.c.participant_id, ts)
            .order_by(series.c.participant_id, ts)
        )
        if participant_id is not None:
            statement = statement.where(series.c.participant_id == participant_id)
        if since is not None:
            statement = statement.where(ts > since)
        result: dict[UUID, list[Point]] = {}
        for row in (await self.session.execute(statement)).mappings():
            p = tuple(float(row[label]) for label in PROBABILITIES) if row[PROBABILITIES[0]] is not None else None
            result.setdefault(row.participant_id, []).append(Point(row.ts, p, float(row.face_ratio)))
        return result

    async def owned(self, meeting_id: UUID, owner_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(meetings.c.meeting_id).where(
                    meetings.c.meeting_id == meeting_id, meetings.c.owner_id == owner_id
                )
            )
        ) is not None
