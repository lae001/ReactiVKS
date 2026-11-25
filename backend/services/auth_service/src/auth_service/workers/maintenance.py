"""Периодическая очистка с транзакцией на пакет."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_service.repositories.maintenance import purge_auth
from vks_common.clock import Clock
from vks_common.db import transaction


async def maintain_auth(sessions: async_sessionmaker[AsyncSession], clock: Clock) -> None:
    async with sessions() as session, transaction(session):
        await purge_auth(session, clock.now())
