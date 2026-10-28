"""Участники и модерация: ``/api/v1/meetings/{id}/participants`` (EMO-70)."""

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import CURRENT_NOTICE
from meeting_service.domain.livekit import MediaKind

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


class LiveKit(Protocol):
    available: bool
    muted: list[tuple[str, str, MediaKind]]
    removed: list[tuple[str, str]]


class Webhooks(Protocol):
    async def send(self, event: str, **fields: object) -> httpx.Response: ...


class Meeting:
    """Идущая встреча организатора с одним гостем."""

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.id = ""
        self.organizer_id = ""
        self.guest_id = ""
        self.guest_token = ""

    async def start(self) -> None:
        created = (await self.client.post(MEETINGS, json={"title": "Планерка"}, headers=self.headers)).json()
        self.id = created["id"]
        joined = await self.client.post(f"{MEETINGS}/{self.id}/join", json={"consent": "granted"}, headers=self.headers)
        self.organizer_id = joined.json()["participant_id"]
        guest = await self.client.post(
            f"/api/v1/join/{created['invite_code']}",
            json={"display_name": "Анна", "consent": "denied", "notice_version": CURRENT_NOTICE.version},
        )
        self.guest_id = guest.json()["participant_id"]
        self.guest_token = guest.json()["participant_token"]

    def path(self, participant_id: str | None = None, action: str = "") -> str:
        base = f"{MEETINGS}/{self.id}/participants"
        return f"{base}/{participant_id}/{action}" if participant_id else base

    async def participants(self) -> list[dict[str, object]]:
        response = await self.client.get(self.path(), headers=self.headers)
        assert response.status_code == 200, response.text
        items: list[dict[str, object]] = response.json()["items"]
        return items


@pytest.fixture
async def meeting(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> Meeting:
    started = Meeting(client, organizer_headers(uuid4()))
    await started.start()
    return started


async def test_participants_show_role_consent_and_presence(meeting: Meeting, webhooks: Webhooks) -> None:
    await webhooks.send("participant_joined", room=meeting.id, identity=f"p_{meeting.guest_id}")

    items = await meeting.participants()

    assert [(item["display_name"], item["role"], item["consent_state"], item["online"]) for item in items] == [
        ("Иван Петров", "organizer", "granted", False),
        ("Анна", "guest", "denied", True),
    ]
    assert items[1]["first_joined_at"] is not None
    assert items[1]["is_removed"] is False


async def test_mute_turns_off_participant_media(meeting: Meeting, livekit: LiveKit) -> None:
    response = await meeting.client.post(
        meeting.path(meeting.guest_id, "mute"), json={"kind": "video"}, headers=meeting.headers
    )

    assert response.status_code == 204
    assert livekit.muted == [(meeting.id, f"p_{meeting.guest_id}", MediaKind.VIDEO)]


async def test_removed_guest_cannot_rejoin_and_leaves_as_removed(
    meeting: Meeting, livekit: LiveKit, webhooks: Webhooks, session: AsyncSession
) -> None:
    await webhooks.send("participant_joined", room=meeting.id, identity=f"p_{meeting.guest_id}")

    response = await meeting.client.post(meeting.path(meeting.guest_id, "remove"), headers=meeting.headers)
    await webhooks.send("participant_left", room=meeting.id, identity=f"p_{meeting.guest_id}")

    assert response.status_code == 204
    assert livekit.removed == [(meeting.id, f"p_{meeting.guest_id}")]
    guest = (await meeting.participants())[1]
    assert (guest["is_removed"], guest["online"]) == (True, False)
    rejoin = await meeting.client.post(
        "/api/v1/participants/me/rejoin", headers={"Authorization": f"Participant {meeting.guest_token}"}
    )
    assert rejoin.status_code == 409
    assert rejoin.json()["code"] == "participant_removed"
    envelope = (
        await session.execute(
            text("SELECT envelope FROM meeting.outbox WHERE event_type = 'participant.left' AND event_key = :key"),
            {"key": meeting.id},
        )
    ).scalar_one()
    assert envelope["payload"]["reason"] == "removed"


async def test_repeated_remove_is_204(meeting: Meeting) -> None:
    path = meeting.path(meeting.guest_id, "remove")

    first = await meeting.client.post(path, headers=meeting.headers)
    repeated = await meeting.client.post(path, headers=meeting.headers)

    assert (first.status_code, repeated.status_code) == (204, 204)


async def test_organizer_cannot_remove_self(meeting: Meeting) -> None:
    response = await meeting.client.post(meeting.path(meeting.organizer_id, "remove"), headers=meeting.headers)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_removal_blocks_rejoin_even_if_livekit_is_down(meeting: Meeting, livekit: LiveKit) -> None:
    livekit.available = False

    response = await meeting.client.post(meeting.path(meeting.guest_id, "remove"), headers=meeting.headers)

    assert response.status_code == 503
    assert response.json()["code"] == "livekit_unavailable"
    assert (await meeting.participants())[1]["is_removed"] is True


async def test_moderation_after_meeting_ended_is_409(meeting: Meeting) -> None:
    await meeting.client.post(f"{MEETINGS}/{meeting.id}/end", headers=meeting.headers)

    muted = await meeting.client.post(
        meeting.path(meeting.guest_id, "mute"), json={"kind": "audio"}, headers=meeting.headers
    )
    removed = await meeting.client.post(meeting.path(meeting.guest_id, "remove"), headers=meeting.headers)

    assert (muted.json()["code"], removed.json()["code"]) == ("meeting_ended", "meeting_ended")


async def test_foreign_meeting_is_404(meeting: Meeting, organizer_headers: OrganizerHeaders) -> None:
    stranger = organizer_headers()

    listed = await meeting.client.get(meeting.path(), headers=stranger)
    muted = await meeting.client.post(meeting.path(meeting.guest_id, "mute"), json={"kind": "audio"}, headers=stranger)
    removed = await meeting.client.post(meeting.path(meeting.guest_id, "remove"), headers=stranger)

    assert {listed.status_code, muted.status_code, removed.status_code} == {404}


async def test_unknown_participant_is_404(meeting: Meeting) -> None:
    response = await meeting.client.post(meeting.path(str(uuid4()), "remove"), headers=meeting.headers)

    assert response.status_code == 404


async def test_moderation_requires_access_token(meeting: Meeting) -> None:
    listed = await meeting.client.get(meeting.path())
    muted = await meeting.client.post(meeting.path(meeting.guest_id, "mute"), json={"kind": "audio"})

    assert (listed.status_code, muted.status_code) == (401, 401)


@pytest.mark.parametrize("body", [{"kind": "screen"}, {}])
async def test_invalid_mute_is_422(meeting: Meeting, body: dict[str, str]) -> None:
    response = await meeting.client.post(meeting.path(meeting.guest_id, "mute"), json=body, headers=meeting.headers)

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "kind"]
