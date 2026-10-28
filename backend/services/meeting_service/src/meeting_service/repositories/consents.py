"""Журнал согласий: ``meeting.consents`` – только добавление."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import ConsentRecord
from meeting_service.models import ConsentRow

__all__ = ["ConsentLog"]


class ConsentLog:
    """Работает в транзакции вызывающего сценария: решение пишется вместе с изменением участника."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, record: ConsentRecord) -> None:
        self._session.add(
            ConsentRow(
                meeting_id=record.meeting_id,
                participant_id=record.participant_id,
                display_name=record.display_name,
                meeting_title=record.meeting_title,
                decision=record.decision.value,
                notice_version=record.notice_version,
                ip=record.ip,
                user_agent=record.user_agent,
                decided_at=record.decided_at,
            )
        )
        await self._session.flush()
