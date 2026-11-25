"""Кандидаты сверки и очистка служебных записей meeting-service."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import MeetingId
from meeting_service.models import OUTBOX, ConsentRow, MeetingRow, ProcessedWebhookRow


async def candidates(session: AsyncSession, now: datetime) -> list[MeetingId]:
    return [
        MeetingId(value)
        for value in await session.scalars(
            select(MeetingRow.id)
            .where(
                MeetingRow.deleted_at.is_(None),
                (
                    (MeetingRow.status == "active")
                    | ((MeetingRow.status == "scheduled") & (MeetingRow.scheduled_at < now - timedelta(hours=24)))
                ),
            )
            .order_by(MeetingRow.id)
        )
    ]


async def purge_meetings(session: AsyncSession, now: datetime) -> None:
    old = select(MeetingRow.id).where(MeetingRow.deleted_at < now - timedelta(days=30)).limit(100)
    await session.execute(delete(MeetingRow).where(MeetingRow.id.in_(old)))
    consents = select(ConsentRow.id).where(ConsentRow.decided_at < now - timedelta(days=3 * 365)).limit(5000)
    await session.execute(delete(ConsentRow).where(ConsentRow.id.in_(consents)))
    webhooks = (
        select(ProcessedWebhookRow.event_id)
        .where(ProcessedWebhookRow.received_at < now - timedelta(days=7))
        .limit(5000)
    )
    await session.execute(delete(ProcessedWebhookRow).where(ProcessedWebhookRow.event_id.in_(webhooks)))
    outbox = select(OUTBOX.c.id).where(OUTBOX.c.published_at < now - timedelta(days=7)).limit(5000)
    await session.execute(delete(OUTBOX).where(OUTBOX.c.id.in_(outbox)))


async def missing_since(session: AsyncSession, meeting_id: MeetingId, now: datetime, present: bool) -> datetime | None:
    return await session.scalar(
        update(MeetingRow)
        .where(MeetingRow.id == meeting_id)
        .values(room_missing_since=None if present else func.coalesce(MeetingRow.room_missing_since, now))
        .returning(MeetingRow.room_missing_since)
    )


async def should_close(session: AsyncSession, meeting_id: UUID) -> bool:
    row = await session.get(MeetingRow, meeting_id)
    return row is not None and (row.deleted_at is not None or row.status in ("ended", "cancelled"))
