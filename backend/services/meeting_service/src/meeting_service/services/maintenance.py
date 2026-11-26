"""Сверка комнат и переходы статуса с событиями outbox."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_service.domain.identifiers import MeetingId
from meeting_service.domain.meetings import EndReason, MeetingStatus
from meeting_service.repositories.maintenance import candidates, missing_since, purge_meetings, should_close
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.outbox import EventOutbox
from meeting_service.services.event_payloads import meeting_closed
from vks_common.clock import Clock
from vks_common.db import transaction


class RoomCatalog(Protocol):
    async def list_rooms(self) -> Mapping[str, int]: ...
    async def delete_room(self, room: str) -> None: ...


async def maintain_meetings(sessions: async_sessionmaker[AsyncSession], clock: Clock, livekit: RoomCatalog) -> None:
    async with sessions() as session, transaction(session):
        await purge_meetings(session, clock.now())
    rooms = await livekit.list_rooms()
    now = clock.now()
    async with sessions() as session, transaction(session):
        ids = await candidates(session, now)
    for meeting_id in ids:
        async with sessions() as session, transaction(session):
            repository = MeetingRepository(session)
            meeting = await repository.lock(meeting_id)
            if meeting is None:
                continue
            absent = await missing_since(session, meeting_id, now, str(meeting_id) in rooms)
            if meeting.status is MeetingStatus.SCHEDULED:
                closed = meeting.closed(now)
            elif absent is not None and now - absent >= timedelta(minutes=2):
                closed = meeting.ended(now, EndReason.EMPTY_TIMEOUT)
            else:
                continue
            await repository.save_lifecycle(closed, now=now)
            await EventOutbox(session).add(meeting_closed(closed), occurred_at=now)
    for name in rooms:
        try:
            identity = MeetingId(UUID(name))
        except ValueError:
            continue
        async with sessions() as session, transaction(session):
            close = await should_close(session, identity)
        if close:
            await livekit.delete_room(name)
