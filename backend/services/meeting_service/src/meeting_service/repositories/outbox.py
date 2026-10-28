"""События ``meeting.events`` в ``meeting.outbox`` – в транзакции вызывающего сценария (ADR-011)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.models import OUTBOX
from vks_common.ids import new_id
from vks_common.kafka import OutboxWriter
from vks_contracts import EventPayload

__all__ = ["PRODUCER", "EventOutbox"]

# Поле producer конверта.
PRODUCER = "meeting-service"


class EventOutbox:
    """Публикация события – запись в outbox; в Kafka его отправит релей после фиксации транзакции."""

    def __init__(self, session: AsyncSession) -> None:
        self._writer = OutboxWriter(session, OUTBOX, producer=PRODUCER)

    async def add(self, payload: EventPayload, *, occurred_at: datetime) -> None:
        await self._writer.add(payload, event_id=new_id(), occurred_at=occurred_at)
