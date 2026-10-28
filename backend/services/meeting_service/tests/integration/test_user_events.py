"""Обработчик user.events: проекция блокировок и удаление встреч удаленного организатора (EMO-69)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_service.consumers.user_events import UserEventsHandler
from meeting_service.domain.livekit import MediaKind, RoomAccess
from vks_common.clock import FixedClock
from vks_contracts import EventPayload, ParsedEvent
from vks_contracts.envelope import envelope_for
from vks_contracts.ml_events import MlStatus
from vks_contracts.user_events import UserBlocked, UserDeleted, UserUnblocked

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


class LiveKit(Protocol):
    available: bool
    deleted: list[str]
    issued: list[RoomAccess]

    async def ensure_room(self, room: str) -> None: ...
    async def delete_room(self, room: str) -> None: ...
    def issue_token(self, access: RoomAccess) -> str: ...
    async def mute(self, room: str, identity: str, kind: MediaKind) -> None: ...
    async def remove(self, room: str, identity: str) -> None: ...
    @property
    def public_url(self) -> str: ...


def parsed(payload: EventPayload) -> ParsedEvent:
    envelope = envelope_for(
        payload, event_id=uuid4(), occurred_at=datetime(2026, 11, 20, 7, 0, tzinfo=UTC), producer="auth-service"
    )
    return ParsedEvent(envelope=envelope, payload=payload)


@pytest.fixture
def handler(
    session_factory: async_sessionmaker[AsyncSession], clock: FixedClock, livekit: LiveKit
) -> UserEventsHandler:
    return UserEventsHandler(session_factory=session_factory, clock=clock, livekit=livekit)


async def create(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    meeting: dict[str, str] = (await client.post(MEETINGS, json={"title": "Планерка"}, headers=headers)).json()
    return meeting


async def join(client: httpx.AsyncClient, headers: dict[str, str], meeting: dict[str, str]) -> httpx.Response:
    return await client.post(f"{MEETINGS}/{meeting['id']}/join", json={"consent": "granted"}, headers=headers)


async def test_blocked_organizer_cannot_enter_meetings(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, handler: UserEventsHandler
) -> None:
    user_id = uuid4()
    headers = organizer_headers(user_id)
    meeting = await create(client, headers)

    await handler(parsed(UserBlocked(user_id=user_id)))

    response = await join(client, headers, meeting)
    assert response.status_code == 403
    assert response.json()["code"] == "user_blocked"


async def test_unblocked_organizer_enters_again(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, handler: UserEventsHandler
) -> None:
    user_id = uuid4()
    headers = organizer_headers(user_id)
    meeting = await create(client, headers)

    await handler(parsed(UserBlocked(user_id=user_id)))
    await handler(parsed(UserUnblocked(user_id=user_id)))

    assert (await join(client, headers, meeting)).status_code == 200


async def test_repeated_block_events_are_idempotent(handler: UserEventsHandler, session: AsyncSession) -> None:
    user_id = uuid4()

    for _ in range(2):
        await handler(parsed(UserBlocked(user_id=user_id)))
    for _ in range(2):
        await handler(parsed(UserUnblocked(user_id=user_id)))

    count = (
        await session.execute(text("SELECT count(*) FROM meeting.blocked_users WHERE user_id = :id"), {"id": user_id})
    ).scalar_one()
    assert count == 0


async def test_deleted_user_loses_all_meetings(
    client: httpx.AsyncClient,
    organizer_headers: OrganizerHeaders,
    handler: UserEventsHandler,
    session: AsyncSession,
    livekit: LiveKit,
) -> None:
    user_id = uuid4()
    headers = organizer_headers(user_id)
    scheduled = await create(client, headers)
    active = await create(client, headers)
    await join(client, headers, active)
    other = await create(client, organizer_headers())

    await handler(parsed(UserDeleted(user_id=user_id)))

    assert (await client.get(MEETINGS, headers=headers)).json()["items"] == []
    assert livekit.deleted == [active["id"]]
    assert await deleted_events(session) == {scheduled["id"], active["id"]}
    assert other["id"] not in await deleted_events(session)


async def test_repeated_user_deleted_publishes_nothing_new(
    client: httpx.AsyncClient,
    organizer_headers: OrganizerHeaders,
    handler: UserEventsHandler,
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await create(client, organizer_headers(user_id))
    event = parsed(UserDeleted(user_id=user_id))

    await handler(event)
    await handler(event)

    assert len(await deleted_events(session)) == 1


async def test_other_events_on_topic_are_ignored(handler: UserEventsHandler, session: AsyncSession) -> None:
    status = MlStatus(meeting_id=uuid4(), state="active", effective_fps=3.0, target_fps=3, worker_id="ml-1")

    await handler(parsed(status))

    assert (await session.execute(text("SELECT count(*) FROM meeting.blocked_users"))).scalar_one() == 0


async def deleted_events(session: AsyncSession) -> set[str]:
    rows = await session.execute(text("SELECT event_key FROM meeting.outbox WHERE event_type = 'meeting.deleted'"))
    return {str(UUID(key)) for key in rows.scalars()}
