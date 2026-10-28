"""Обработанные вебхуки LiveKit: ``meeting.processed_webhooks``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.models import ProcessedWebhookRow

__all__ = ["ProcessedWebhooks"]


class ProcessedWebhooks:
    """Работает в транзакции вызывающего сценария: отметка и эффект вебхука фиксируются вместе."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(self, event_id: str, *, now: datetime) -> bool:
        """Отметить вебхук обработанным; ``False`` – он уже был (повторная доставка).

        ``ON CONFLICT DO NOTHING``: одновременная повторная доставка ждет фиксации первой и тоже получает ``False``.
        """
        statement = (
            insert(ProcessedWebhookRow)
            .values(event_id=event_id, received_at=now)
            .on_conflict_do_nothing(index_elements=[ProcessedWebhookRow.event_id])
            .returning(ProcessedWebhookRow.event_id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None
