"""Доставка одного задания с короткими транзакциями до и после RPC."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.errors import LiveKitUnavailable
from meeting_service.domain.identifiers import ParticipantId
from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.domain.participants import ConsentState
from meeting_service.repositories.livekit_sync import LiveKitSyncQueue
from vks_common.clock import Clock
from vks_common.db import transaction

_LEASE = timedelta(seconds=30)


class SyncLiveKitConsent:
    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._clock = clock
        self._livekit = livekit
        self._queue = LiveKitSyncQueue(session)

    async def execute(self, *, participant_id: ParticipantId | None = None) -> bool:
        now = self._clock.now()
        async with transaction(self._session):
            job = await self._queue.claim(now=now, locked_until=now + _LEASE, participant_id=participant_id)
        if job is None:
            return False

        retry_at = None
        try:
            await self._livekit.update_attributes(job.room, job.identity, job.attributes)
        except LiveKitUnavailable:
            delay = 1 if job.attributes["vks.consent"] == ConsentState.REVOKED else min(2 ** min(job.attempts, 6), 60)
            retry_at = self._clock.now() + timedelta(seconds=delay)

        async with transaction(self._session):
            return await self._queue.finish(job, retry_at=retry_at)
