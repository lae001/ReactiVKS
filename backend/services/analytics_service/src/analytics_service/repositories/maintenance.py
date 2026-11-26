"""Срок хранения аналитики: физическое удаление с защитой от повторных событий."""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.models import OUTBOX, meetings
from analytics_service.repositories.projections import Projections


async def purge_analytics(session: AsyncSession, now: datetime, retention_days: int) -> None:
    ids = list(
        await session.scalars(
            select(meetings.c.meeting_id)
            .where(meetings.c.ended_at < now - timedelta(days=retention_days))
            .order_by(meetings.c.meeting_id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    )
    for meeting_id in ids:
        await Projections(session).remove_meeting(meeting_id)
    old = select(OUTBOX.c.id).where(OUTBOX.c.published_at < now - timedelta(days=7)).limit(5000)
    await session.execute(delete(OUTBOX).where(OUTBOX.c.id.in_(old)))
