"""Сверка LiveKit: задержка закрытия, отмена и защита чужих комнат."""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_service.domain.identifiers import MeetingId
from meeting_service.models import MeetingRow
from meeting_service.services.maintenance import maintain_meetings
from vks_common.clock import FixedClock
from vks_common.testing import TokenFactory

pytestmark = pytest.mark.integration


class Rooms:
    def __init__(self) -> None:
        self.rooms: dict[str, int] = {}
        self.closed: list[str] = []

    async def list_rooms(self) -> Mapping[str, int]:
        return self.rooms.copy()

    async def delete_room(self, name: str) -> None:
        self.closed.append(name)
        self.rooms.pop(name, None)


async def test_reconciliation_grace_and_foreign_room(
    client: httpx.AsyncClient,
    tokens: TokenFactory,
    session_factory: async_sessionmaker[AsyncSession],
    clock: FixedClock,
) -> None:
    headers = {"Authorization": "Bearer " + tokens.issue()}
    created = await client.post("/api/v1/meetings", headers=headers, json={"title": "Сверка"})
    meeting_id = MeetingId(UUID(created.json()["id"]))
    async with session_factory() as session, session.begin():
        await session.execute(
            update(MeetingRow)
            .where(MeetingRow.id == meeting_id)
            .values(status="active", started_at=clock.now() - timedelta(minutes=5))
        )
    rooms = Rooms()
    foreign = str(uuid4())
    rooms.rooms[foreign] = 1
    await maintain_meetings(session_factory, clock, rooms)
    async with session_factory() as session:
        assert await session.scalar(select(MeetingRow.status).where(MeetingRow.id == meeting_id)) == "active"
    later = FixedClock(clock.now() + timedelta(seconds=121))
    await maintain_meetings(session_factory, later, rooms)
    async with session_factory() as session:
        assert await session.scalar(select(MeetingRow.status).where(MeetingRow.id == meeting_id)) == "ended"
    rooms.rooms[str(meeting_id)] = 1
    await maintain_meetings(session_factory, later, rooms)
    assert rooms.closed == [str(meeting_id)]
    assert foreign in rooms.rooms


async def test_stale_schedule_cancelled(
    client: httpx.AsyncClient,
    tokens: TokenFactory,
    session_factory: async_sessionmaker[AsyncSession],
    clock: FixedClock,
) -> None:
    headers = {"Authorization": "Bearer " + tokens.issue()}
    created = await client.post("/api/v1/meetings", headers=headers, json={"title": "Просрочена"})
    meeting_id = UUID(created.json()["id"])
    async with session_factory() as session, session.begin():
        await session.execute(
            update(MeetingRow).where(MeetingRow.id == meeting_id).values(scheduled_at=clock.now() - timedelta(hours=25))
        )
    await maintain_meetings(session_factory, clock, Rooms())
    assert (await client.get(f"/api/v1/meetings/{meeting_id}", headers=headers)).json()["status"] == "cancelled"
