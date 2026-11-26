"""Очистка аналитики в транзакции."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.repositories.maintenance import purge_analytics
from vks_common.clock import Clock
from vks_common.db import transaction


async def maintain_analytics(sessions: async_sessionmaker[AsyncSession], clock: Clock, days: int) -> None:
    async with sessions() as session, transaction(session):
        await purge_analytics(session, clock.now(), days)
