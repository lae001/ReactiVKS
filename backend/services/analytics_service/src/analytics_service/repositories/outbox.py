"""Запись событий отчета в транзакционный outbox."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.models import OUTBOX
from vks_common.ids import new_id
from vks_common.kafka import OutboxWriter
from vks_contracts import EventPayload


class ReportOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._writer = OutboxWriter(session, OUTBOX, producer="analytics-service")

    async def add(self, payload: EventPayload, now: datetime) -> None:
        await self._writer.add(payload, event_id=new_id(), occurred_at=now)
