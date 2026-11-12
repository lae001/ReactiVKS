"""Изменение согласия через HTTP и повтор доставки атрибутов LiveKit."""

from collections.abc import Callable
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.services.livekit_sync import SyncLiveKitConsent
from vks_common.clock import FixedClock

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"
CONSENT = "/api/v1/participants/me/consent"
REVOKED = {"decision": "revoked"}

ActiveMeeting = tuple[dict[str, str], dict[str, str]]
Guest = tuple[str, dict[str, str]]


class LiveKit(LiveKitGateway, Protocol):
    available: bool
    updated: list[tuple[str, str, dict[str, str]]]


@pytest.fixture
async def active_meeting(client: httpx.AsyncClient, organizer_headers: Callable[..., dict[str, str]]) -> ActiveMeeting:
    headers = organizer_headers(uuid4())
    created = await client.post(MEETINGS, json={"title": "Демонстрация"}, headers=headers)
    assert created.status_code == 201, created.text
    meeting = created.json()
    joined = await client.post(f"{MEETINGS}/{meeting['id']}/join", json={"consent": "granted"}, headers=headers)
    assert joined.status_code == 200, joined.text
    return meeting, headers


@pytest.fixture
async def guest(client: httpx.AsyncClient, active_meeting: ActiveMeeting) -> Guest:
    meeting, _ = active_meeting
    path = f"/api/v1/join/{meeting['invite_code']}"
    notice = (await client.get(path)).json()["consent_notice"]["version"]
    joined = await client.post(path, json={"display_name": "Анна", "consent": "granted", "notice_version": notice})
    assert joined.status_code == 200, joined.text
    body = joined.json()
    return body["participant_id"], {"Authorization": f"Participant {body['participant_token']}"}


async def test_guest_revokes_then_grants(
    client: httpx.AsyncClient, guest: Guest, livekit: LiveKit, session: AsyncSession
) -> None:
    participant_id, headers = guest

    revoked = await client.put(CONSENT, json=REVOKED, headers=headers)
    granted = await client.put(CONSENT, json={"decision": "granted"}, headers=headers)

    assert revoked.status_code == granted.status_code == 200
    assert revoked.json() == {"consent_state": "revoked", "synced": True}
    assert granted.json() == {"consent_state": "granted", "synced": True}
    assert [(identity, attrs["vks.consent"]) for _, identity, attrs in livekit.updated] == [
        (f"p_{participant_id}", "revoked"),
        (f"p_{participant_id}", "granted"),
    ]
    journal = await session.scalars(
        text("SELECT decision FROM meeting.consents WHERE participant_id = CAST(:id AS uuid) ORDER BY id"),
        {"id": participant_id},
    )
    assert journal.all() == ["granted", "revoked", "granted"]


async def test_organizer_updates_own_consent(client: httpx.AsyncClient, active_meeting: ActiveMeeting) -> None:
    meeting, headers = active_meeting

    response = await client.put(CONSENT, params={"meeting_id": meeting["id"]}, json=REVOKED, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"consent_state": "revoked", "synced": True}


async def test_guest_change_is_retried_after_livekit_failure(
    client: httpx.AsyncClient, guest: Guest, livekit: LiveKit, clock: FixedClock, session: AsyncSession
) -> None:
    participant_id, headers = guest
    livekit.available = False

    response = await client.put(CONSENT, json=REVOKED, headers=headers)

    assert response.status_code == 202
    assert response.json() == {"consent_state": "revoked", "synced": False}
    assert not livekit.updated

    livekit.available = True
    clock.advance(timedelta(seconds=1))
    synced = await SyncLiveKitConsent(session=session, clock=clock, livekit=livekit).execute()

    assert synced
    assert livekit.updated[-1][1:] == (f"p_{participant_id}", {"vks.consent": "revoked"})


async def test_rejects_unauthenticated_consent(client: httpx.AsyncClient) -> None:
    response = await client.put(CONSENT, json=REVOKED)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_organizer_cannot_update_consent_in_another_meeting(
    client: httpx.AsyncClient, active_meeting: ActiveMeeting, organizer_headers: Callable[..., dict[str, str]]
) -> None:
    meeting, _ = active_meeting

    response = await client.put(
        CONSENT, params={"meeting_id": meeting["id"]}, json=REVOKED, headers=organizer_headers(uuid4())
    )

    assert response.status_code == 404


async def test_removed_guest_cannot_grant_consent(
    client: httpx.AsyncClient, active_meeting: ActiveMeeting, guest: Guest
) -> None:
    meeting, organizer_headers = active_meeting
    participant_id, headers = guest
    removed = await client.post(
        f"{MEETINGS}/{meeting['id']}/participants/{participant_id}/remove", headers=organizer_headers
    )
    assert removed.status_code == 204

    response = await client.put(CONSENT, json={"decision": "granted"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "participant_removed"
