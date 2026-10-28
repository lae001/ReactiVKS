from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import CURRENT_NOTICE
from meeting_service.domain.livekit import RoomAccess

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"
NOTICE = CURRENT_NOTICE.version

OrganizerHeaders = Callable[..., dict[str, str]]


class LiveKit(Protocol):
    available: bool
    rooms: set[str]
    deleted: list[str]
    issued: list[RoomAccess]


class Organizer:
    """Организатор с одной встречей – то, с чего начинается каждый сценарий входа."""

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.meeting: dict[str, str] = {}

    async def create(self, **body: object) -> dict[str, str]:
        response = await self.client.post(MEETINGS, json={"title": "Планерка"} | body, headers=self.headers)
        assert response.status_code == 201, response.text
        self.meeting = response.json()
        return self.meeting

    async def join(self, **body: object) -> httpx.Response:
        return await self.client.post(
            f"{MEETINGS}/{self.meeting['id']}/join", json=body or {"consent": "granted"}, headers=self.headers
        )

    async def end(self) -> httpx.Response:
        return await self.client.post(f"{MEETINGS}/{self.meeting['id']}/end", headers=self.headers)

    @property
    def join_path(self) -> str:
        return f"/api/v1/join/{self.meeting['invite_code']}"


@pytest.fixture
def organizer(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> Organizer:
    return Organizer(client, organizer_headers(uuid4(), name="Иван Петров"))


async def guest_join(client: httpx.AsyncClient, path: str, **body: object) -> httpx.Response:
    return await client.post(path, json={"display_name": "Анна", "consent": "granted", "notice_version": NOTICE} | body)


# --- вход организатора ----------------------------------------------------------------------------------------------


async def test_first_organizer_join_starts_meeting_and_creates_room(organizer: Organizer, livekit: LiveKit) -> None:
    meeting = await organizer.create()

    response = await organizer.join()

    assert response.status_code == 200
    body = response.json()
    assert body["meeting"] == {"id": meeting["id"], "title": "Планерка", "status": "active", "analysis_enabled": True}
    assert body["livekit_url"] == "ws://livekit.test:7880"
    assert meeting["id"] in livekit.rooms
    access = livekit.issued[-1]
    assert access.room == meeting["id"]
    assert access.identity == f"p_{body['participant_id']}"
    assert access.name == "Иван Петров"
    assert dict(access.attributes) == {"vks.role": "organizer", "vks.consent": "granted", "vks.kind": "human"}


async def test_organizer_is_one_participant_however_many_times_he_joins(
    organizer: Organizer, client: httpx.AsyncClient
) -> None:
    await organizer.create()

    first = await organizer.join()
    second = await organizer.join(consent="denied")

    assert first.json()["participant_id"] == second.json()["participant_id"]
    card = await client.get(f"{MEETINGS}/{organizer.meeting['id']}", headers=organizer.headers)
    assert card.json()["participants_count"] == 1
    assert card.json()["started_at"] is not None


async def test_organizer_join_records_consent_decisions(organizer: Organizer, session: AsyncSession) -> None:
    await organizer.create()

    await organizer.join(consent="granted")
    await organizer.join(consent="denied")

    rows = await session.execute(
        text("SELECT decision, notice_version FROM meeting.consents WHERE meeting_id = :id ORDER BY id"),
        {"id": UUID(organizer.meeting["id"])},
    )
    assert [tuple(row) for row in rows] == [("granted", NOTICE), ("denied", NOTICE)]


async def test_organizer_join_requires_consent_when_analysis_is_enabled(organizer: Organizer) -> None:
    await organizer.create()

    response = await organizer.client.post(f"{MEETINGS}/{organizer.meeting['id']}/join", headers=organizer.headers)

    assert response.status_code == 409
    assert response.json()["code"] == "consent_required"


async def test_organizer_joins_without_consent_when_analysis_is_off(organizer: Organizer, livekit: LiveKit) -> None:
    await organizer.create(analysis_enabled=False)

    response = await organizer.client.post(f"{MEETINGS}/{organizer.meeting['id']}/join", headers=organizer.headers)

    assert response.status_code == 200
    assert livekit.issued[-1].attributes["vks.consent"] == "not_required"


async def test_join_of_foreign_meeting_is_404(organizer: Organizer, organizer_headers: OrganizerHeaders) -> None:
    await organizer.create()

    response = await organizer.client.post(
        f"{MEETINGS}/{organizer.meeting['id']}/join", json={"consent": "granted"}, headers=organizer_headers()
    )

    assert response.status_code == 404


async def test_join_requires_access_token(organizer: Organizer) -> None:
    await organizer.create()

    response = await organizer.client.post(f"{MEETINGS}/{organizer.meeting['id']}/join", json={"consent": "granted"})

    assert response.status_code == 401


async def test_meeting_stays_scheduled_when_livekit_is_unavailable(
    organizer: Organizer, livekit: LiveKit, client: httpx.AsyncClient
) -> None:
    await organizer.create()
    livekit.available = False

    response = await organizer.join()

    assert response.status_code == 503
    assert response.json()["code"] == "livekit_unavailable"
    card = await client.get(f"{MEETINGS}/{organizer.meeting['id']}", headers=organizer.headers)
    assert card.json()["status"] == "scheduled"


# --- лобби и вход гостя ---------------------------------------------------------------------------------------------


async def test_lobby_shows_meeting_organizer_and_consent_notice(
    organizer: Organizer, client: httpx.AsyncClient
) -> None:
    await organizer.create(scheduled_at="2026-11-20T07:00:00Z")

    response = await client.get(organizer.join_path)

    assert response.status_code == 200
    assert response.json() == {
        "title": "Планерка",
        "organizer_name": "Иван Петров",
        "status": "scheduled",
        "scheduled_at": "2026-11-20T07:00:00Z",
        "analysis_enabled": True,
        "consent_notice": {"version": NOTICE, "text_md": CURRENT_NOTICE.text_md},
    }


async def test_lobby_has_no_consent_notice_when_analysis_is_off(
    organizer: Organizer, client: httpx.AsyncClient
) -> None:
    await organizer.create(analysis_enabled=False)

    response = await client.get(organizer.join_path)

    assert response.json()["consent_notice"] is None


@pytest.mark.parametrize("invite_code", ["zzzzzzzzzz", "NOT-A-CODE", "k3m7qx4tp1"])
async def test_unknown_invite_is_404(client: httpx.AsyncClient, invite_code: str) -> None:
    response = await client.get(f"/api/v1/join/{invite_code}")

    assert response.status_code == 404


async def test_guest_cannot_join_before_organizer(organizer: Organizer, client: httpx.AsyncClient) -> None:
    await organizer.create()

    response = await guest_join(client, organizer.join_path)

    assert response.status_code == 409
    assert response.json()["code"] == "meeting_not_started"


async def test_guest_joins_active_meeting(organizer: Organizer, client: httpx.AsyncClient, livekit: LiveKit) -> None:
    await organizer.create()
    await organizer.join()

    response = await guest_join(client, organizer.join_path, display_name="  Анна  ")

    assert response.status_code == 200
    body = response.json()
    assert body["participant_token"].startswith("pt_")
    assert body["meeting"]["status"] == "active"
    access = livekit.issued[-1]
    assert access.name == "Анна"
    assert dict(access.attributes) == {"vks.role": "guest", "vks.consent": "granted", "vks.kind": "human"}


async def test_guest_token_is_stored_only_as_hash(
    organizer: Organizer, client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await organizer.create()
    await organizer.join()

    body = (await guest_join(client, organizer.join_path)).json()

    stored = await session.execute(
        text("SELECT participant_token_hash FROM meeting.participants WHERE id = :id"),
        {"id": UUID(body["participant_id"])},
    )
    token_hash = stored.scalar_one()
    assert len(token_hash) == 32
    assert body["participant_token"].encode() not in token_hash


async def test_guest_decision_is_logged_with_origin(
    organizer: Organizer, client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await organizer.create()
    await organizer.join()

    body = (await guest_join(client, organizer.join_path, consent="denied")).json()

    row = await session.execute(
        text(
            "SELECT decision, display_name, meeting_title, notice_version FROM meeting.consents "
            "WHERE participant_id = :id"
        ),
        {"id": UUID(body["participant_id"])},
    )
    assert tuple(row.one()) == ("denied", "Анна", "Планерка", NOTICE)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        pytest.param({"consent": None}, "consent_required", id="no-decision"),
        pytest.param({"notice_version": None}, "consent_required", id="no-notice-version"),
        pytest.param({"notice_version": "v0"}, "notice_outdated", id="outdated-notice"),
    ],
)
async def test_guest_must_decide_on_current_notice(
    organizer: Organizer, client: httpx.AsyncClient, body: dict[str, object], code: str
) -> None:
    await organizer.create()
    await organizer.join()

    response = await guest_join(client, organizer.join_path, **body)

    assert response.status_code == 409
    assert response.json()["code"] == code


async def test_guest_joins_without_consent_when_analysis_is_off(
    organizer: Organizer, client: httpx.AsyncClient, livekit: LiveKit
) -> None:
    await organizer.create(analysis_enabled=False)
    await organizer.join()

    response = await client.post(organizer.join_path, json={"display_name": "Анна"})

    assert response.status_code == 200
    assert livekit.issued[-1].attributes["vks.consent"] == "not_required"


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 65])
async def test_invalid_guest_name_is_422(organizer: Organizer, client: httpx.AsyncClient, display_name: str) -> None:
    await organizer.create()
    await organizer.join()

    response = await guest_join(client, organizer.join_path, display_name=display_name)

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "display_name"]


# --- повторный вход гостя -------------------------------------------------------------------------------------------


async def test_guest_rejoins_with_participant_token(
    organizer: Organizer, client: httpx.AsyncClient, livekit: LiveKit
) -> None:
    await organizer.create()
    await organizer.join()
    joined = (await guest_join(client, organizer.join_path)).json()

    response = await client.post(
        "/api/v1/participants/me/rejoin", headers={"Authorization": f"Participant {joined['participant_token']}"}
    )

    assert response.status_code == 200
    assert response.json()["participant_id"] == joined["participant_id"]
    assert livekit.issued[-1].identity == f"p_{joined['participant_id']}"


@pytest.mark.parametrize(
    "authorization",
    [None, "Participant pt_unknown", "Bearer pt_whatever", "Participant not-a-participant-token"],
)
async def test_rejoin_without_valid_participant_token_is_401(
    client: httpx.AsyncClient, authorization: str | None
) -> None:
    headers = {"Authorization": authorization} if authorization else {}

    response = await client.post("/api/v1/participants/me/rejoin", headers=headers)

    assert response.status_code == 401


# --- завершение -----------------------------------------------------------------------------------------------------


async def test_end_closes_room_and_is_idempotent(
    organizer: Organizer, client: httpx.AsyncClient, livekit: LiveKit
) -> None:
    await organizer.create()
    await organizer.join()

    first = await organizer.end()
    second = await organizer.end()

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "ended"
    assert first.json()["ended_at"] == second.json()["ended_at"]
    assert livekit.deleted == [organizer.meeting["id"]]


async def test_nobody_joins_ended_meeting(organizer: Organizer, client: httpx.AsyncClient) -> None:
    await organizer.create()
    await organizer.join()
    joined = (await guest_join(client, organizer.join_path)).json()
    await organizer.end()

    as_guest = await guest_join(client, organizer.join_path)
    as_organizer = await organizer.join()
    rejoin = await client.post(
        "/api/v1/participants/me/rejoin", headers={"Authorization": f"Participant {joined['participant_token']}"}
    )

    assert [as_guest.json()["code"], as_organizer.json()["code"], rejoin.json()["code"]] == ["meeting_ended"] * 3


async def test_meeting_ends_even_when_livekit_is_unavailable(organizer: Organizer, livekit: LiveKit) -> None:
    await organizer.create()
    await organizer.join()
    livekit.available = False

    response = await organizer.end()

    assert response.status_code == 200
    assert response.json()["status"] == "ended"
