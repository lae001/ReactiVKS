"""Вебхуки LiveKit: присутствие участников, закрытие пустой комнаты, предел встречи (EMO-69)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import CURRENT_NOTICE

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


class Webhooks(Protocol):
    def body(self, event: str, **fields: object) -> str: ...
    def sign(self, body: str) -> str: ...
    async def post(self, body: str, *, authorization: str | None = None) -> httpx.Response: ...
    async def send(self, event: str, **fields: object) -> httpx.Response: ...


class Room:
    """Идущая встреча: организатор вошел, гости входят по коду приглашения."""

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.meeting: dict[str, str] = {}
        self.organizer_id = ""

    async def open(self) -> None:
        self.meeting = (await self.client.post(MEETINGS, json={"title": "Планерка"}, headers=self.headers)).json()
        joined = await self.join_organizer()
        assert joined.status_code == 200, joined.text
        self.organizer_id = joined.json()["participant_id"]

    async def join_organizer(self) -> httpx.Response:
        return await self.client.post(
            f"{MEETINGS}/{self.meeting['id']}/join", json={"consent": "granted"}, headers=self.headers
        )

    async def join_guest(self, name: str = "Анна") -> httpx.Response:
        return await self.client.post(
            f"/api/v1/join/{self.meeting['invite_code']}",
            json={"display_name": name, "consent": "granted", "notice_version": CURRENT_NOTICE.version},
        )

    async def card(self) -> dict[str, object]:
        card: dict[str, object] = (
            await self.client.get(f"{MEETINGS}/{self.meeting['id']}", headers=self.headers)
        ).json()
        return card


@pytest.fixture
async def room(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> Room:
    opened = Room(client, organizer_headers(uuid4()))
    await opened.open()
    return opened


async def event_types(session: AsyncSession, meeting_id: str) -> list[str]:
    rows = await session.execute(
        text("SELECT event_type FROM meeting.outbox WHERE event_key = :key ORDER BY id"), {"key": meeting_id}
    )
    return list(rows.scalars())


async def presence(session: AsyncSession, participant_id: str) -> tuple[object, object, object]:
    row = (
        await session.execute(
            text("SELECT first_joined_at, last_joined_at, last_left_at FROM meeting.participants WHERE id = :id"),
            {"id": participant_id},
        )
    ).one()
    return row[0], row[1], row[2]


async def test_join_and_leave_are_recorded_and_published(room: Room, webhooks: Webhooks, session: AsyncSession) -> None:
    identity = f"p_{room.organizer_id}"

    await webhooks.send("participant_joined", room=room.meeting["id"], identity=identity)
    await webhooks.send("participant_left", room=room.meeting["id"], identity=identity)

    first_joined, last_joined, last_left = await presence(session, room.organizer_id)
    assert first_joined is not None and first_joined == last_joined
    assert last_left is not None and last_left > last_joined  # type: ignore[operator]  # время из БД
    assert (await event_types(session, room.meeting["id"]))[-2:] == ["participant.joined", "participant.left"]


async def test_repeated_webhook_changes_nothing(room: Room, webhooks: Webhooks, session: AsyncSession) -> None:
    body = webhooks.body("participant_joined", room=room.meeting["id"], identity=f"p_{room.organizer_id}")

    first = await webhooks.post(body)
    repeated = await webhooks.post(body)

    assert (first.status_code, repeated.status_code) == (204, 204)
    assert (await event_types(session, room.meeting["id"])).count("participant.joined") == 1


async def test_late_webhook_does_not_move_presence_back(room: Room, webhooks: Webhooks, session: AsyncSession) -> None:
    identity = f"p_{room.organizer_id}"
    await webhooks.send("participant_joined", room=room.meeting["id"], identity=identity, created_at=1795158100)

    await webhooks.send("participant_joined", room=room.meeting["id"], identity=identity, created_at=1795158000)

    first_joined, last_joined, _ = await presence(session, room.organizer_id)
    assert (first_joined, last_joined) == (
        datetime.fromtimestamp(1795158000, tz=UTC),
        datetime.fromtimestamp(1795158100, tz=UTC),
    )


async def test_agent_presence_is_ignored(room: Room, webhooks: Webhooks, session: AsyncSession) -> None:
    before = await event_types(session, room.meeting["id"])

    await webhooks.send("participant_joined", room=room.meeting["id"], identity="emotion-agent", is_agent=True)

    assert await event_types(session, room.meeting["id"]) == before


async def test_finished_room_ends_active_meeting_by_timeout(
    room: Room, webhooks: Webhooks, session: AsyncSession
) -> None:
    await webhooks.send("room_finished", room=room.meeting["id"])

    assert (await room.card())["status"] == "ended"
    reason = (
        await session.execute(
            text("SELECT end_reason FROM meeting.meetings WHERE id = :id"), {"id": room.meeting["id"]}
        )
    ).scalar_one()
    assert reason == "empty_timeout"
    assert (await event_types(session, room.meeting["id"]))[-1] == "meeting.ended"


async def test_room_closed_after_organizer_ended_meeting_changes_nothing(
    room: Room, webhooks: Webhooks, session: AsyncSession
) -> None:
    await room.client.post(f"{MEETINGS}/{room.meeting['id']}/end", headers=room.headers)

    await webhooks.send("room_finished", room=room.meeting["id"])

    assert (await event_types(session, room.meeting["id"])).count("meeting.ended") == 1


async def test_unknown_events_and_foreign_rooms_are_accepted_and_skipped(
    room: Room, webhooks: Webhooks, session: AsyncSession
) -> None:
    before = await event_types(session, room.meeting["id"])

    await webhooks.send("track_published", room=room.meeting["id"], identity=f"p_{room.organizer_id}")
    await webhooks.send("participant_joined", room="lobby-test", identity=f"p_{room.organizer_id}")
    await webhooks.send("participant_joined", room=room.meeting["id"], identity=f"p_{uuid4()}")

    assert await event_types(session, room.meeting["id"]) == before


@pytest.mark.parametrize("authorization", ["", "Bearer abc", "eyJhbGciOiJIUzI1NiJ9.e30.signature"])
async def test_webhook_without_livekit_signature_is_401(room: Room, webhooks: Webhooks, authorization: str) -> None:
    body = webhooks.body("room_finished", room=room.meeting["id"])

    response = await webhooks.post(body, authorization=authorization or " ")

    assert response.status_code == 401
    assert (await room.card())["status"] == "active"


async def test_webhook_signed_for_other_body_is_401(room: Room, webhooks: Webhooks) -> None:
    body = webhooks.body("room_finished", room=room.meeting["id"])

    response = await webhooks.post(body, authorization=webhooks.sign(body.replace("room_finished", "x")))

    assert response.status_code == 401


async def test_eleventh_participant_gets_meeting_full(room: Room, webhooks: Webhooks) -> None:
    await webhooks.send("participant_joined", room=room.meeting["id"], identity=f"p_{room.organizer_id}")
    for number in range(9):
        guest = await room.join_guest(f"Гость {number}")
        await webhooks.send(
            "participant_joined", room=room.meeting["id"], identity=f"p_{guest.json()['participant_id']}"
        )

    refused = await room.join_guest("Одиннадцатый")
    organizer_again = await room.join_organizer()

    assert refused.status_code == 409
    assert refused.json()["code"] == "meeting_full"
    # Организатор уже в комнате: его повторный вход места не занимает.
    assert organizer_again.status_code == 200


async def test_seat_is_freed_when_participant_leaves(room: Room, webhooks: Webhooks) -> None:
    identities = [f"p_{room.organizer_id}"]
    for number in range(9):
        identities.append(f"p_{(await room.join_guest(f'Гость {number}')).json()['participant_id']}")
    for identity in identities:
        await webhooks.send("participant_joined", room=room.meeting["id"], identity=identity)

    await webhooks.send("participant_left", room=room.meeting["id"], identity=identities[-1])

    assert (await room.join_guest("Новый")).status_code == 200
