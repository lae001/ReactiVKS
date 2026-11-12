"""Фоновая доставка согласия после сбоев LiveKit."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.services.livekit_sync import SyncLiveKitConsent
from vks_common.clock import Clock
from vks_common.logging import get_logger

_logger = get_logger(__name__)


async def run_livekit_sync(
    session_factory: async_sessionmaker[AsyncSession], clock: Clock, livekit: LiveKitGateway
) -> None:
    while True:
        try:
            async with session_factory() as session:
                if await SyncLiveKitConsent(session=session, clock=clock, livekit=livekit).execute():
                    continue
        except SQLAlchemyError:
            _logger.exception("livekit sync database error")
        await asyncio.sleep(0.2)
