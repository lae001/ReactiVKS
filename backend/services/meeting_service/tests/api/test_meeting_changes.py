"""Изменение и удаление встречи: ``PATCH`` и ``DELETE /api/v1/meetings/{id}`` (EMO-68)."""

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


class LiveKit(Protocol):
    available: bool
    deleted: list[str]


async def create(client: httpx.AsyncClient, headers: dict[str, str], **body: object) -> dict[str, object]:
    response = await client.post(MEETINGS, json={"title": "Планерка"} | body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


async def start(client: httpx.AsyncClient, headers: dict[str, str], meeting: dict[str, object]) -> None:
    response = await client.post(f"{MEETINGS}/{meeting['id']}/join", json={"consent": "granted"}, headers=headers)
    assert response.status_code == 200, response.text


async def event_types(session: AsyncSession, meeting_id: object) -> list[str]:
    rows = await session.execute(
        text("SELECT event_type FROM meeting.outbox WHERE event_key = :key ORDER BY id"), {"key": str(meeting_id)}
    )
    return list(rows.scalars())


async def test_patch_changes_only_passed_fields(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers, scheduled_at="2026-11-21T07:00:00Z", analysis_fps=4)

    response = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"title": "Ретро"}, headers=headers)

    assert response.status_code == 200
    assert response.json() == meeting | {"title": "Ретро"}


async def test_patch_with_null_time_turns_meeting_into_instant(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers, scheduled_at="2026-11-21T07:00:00Z")

    response = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"scheduled_at": None}, headers=headers)

    assert response.json()["scheduled_at"] is None


async def test_started_meeting_allows_only_title_change(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)
    await start(client, headers, meeting)

    renamed = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"title": "Итоги"}, headers=headers)
    refused = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"analysis_enabled": False}, headers=headers)

    assert renamed.status_code == 200
    assert refused.status_code == 409
    assert refused.json()["code"] == "meeting_not_editable"


async def test_patch_publishes_update_only_on_change(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, session: AsyncSession
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)

    await client.patch(f"{MEETINGS}/{meeting['id']}", json={"title": "Планерка"}, headers=headers)
    await client.patch(f"{MEETINGS}/{meeting['id']}", json={"analysis_enabled": False}, headers=headers)

    assert await event_types(session, meeting["id"]) == ["meeting.created", "meeting.updated"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        pytest.param({"title": ""}, "title", id="empty-title"),
        pytest.param({"title": "   "}, "title", id="blank-title"),
        pytest.param({"analysis_fps": 1}, "analysis_fps", id="fps-too-low"),
        pytest.param({"scheduled_at": "2026-11-21T07:00:00"}, "scheduled_at", id="naive-time"),
    ],
)
async def test_invalid_patch_is_422(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, body: dict[str, object], field: str
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)

    response = await client.patch(f"{MEETINGS}/{meeting['id']}", json=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", field]


async def test_patch_of_foreign_meeting_is_404(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    meeting = await create(client, organizer_headers())

    response = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"title": "Чужая"}, headers=organizer_headers())

    assert response.status_code == 404


async def test_patch_and_delete_require_access_token(client: httpx.AsyncClient) -> None:
    patched = await client.patch(f"{MEETINGS}/{uuid4()}", json={"title": "Ретро"})
    deleted = await client.delete(f"{MEETINGS}/{uuid4()}")

    assert (patched.status_code, deleted.status_code) == (401, 401)


async def test_deleted_scheduled_meeting_is_cancelled_and_disappears(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, session: AsyncSession
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)

    response = await client.delete(f"{MEETINGS}/{meeting['id']}", headers=headers)

    assert response.status_code == 204
    assert (await client.get(f"{MEETINGS}/{meeting['id']}", headers=headers)).status_code == 404
    assert (await client.get(MEETINGS, headers=headers)).json()["items"] == []
    assert (await client.get(f"/api/v1/join/{meeting['invite_code']}")).status_code == 404
    assert await event_types(session, meeting["id"]) == ["meeting.created", "meeting.cancelled", "meeting.deleted"]


async def test_deleted_active_meeting_is_ended_and_room_closed(
    client: httpx.AsyncClient,
    organizer_headers: OrganizerHeaders,
    session: AsyncSession,
    livekit: LiveKit,
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)
    await start(client, headers, meeting)

    response = await client.delete(f"{MEETINGS}/{meeting['id']}", headers=headers)

    assert response.status_code == 204
    assert livekit.deleted == [meeting["id"]]
    assert (await event_types(session, meeting["id"]))[-2:] == ["meeting.ended", "meeting.deleted"]


async def test_deleted_meeting_is_gone_for_repeated_delete(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)
    await client.delete(f"{MEETINGS}/{meeting['id']}", headers=headers)

    response = await client.delete(f"{MEETINGS}/{meeting['id']}", headers=headers)

    assert response.status_code == 404


async def test_delete_of_foreign_meeting_is_404(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    meeting = await create(client, organizer_headers())

    response = await client.delete(f"{MEETINGS}/{meeting['id']}", headers=organizer_headers())

    assert response.status_code == 404


async def test_active_meeting_is_deleted_even_if_livekit_is_down(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, livekit: LiveKit
) -> None:
    headers = organizer_headers(uuid4())
    meeting = await create(client, headers)
    await start(client, headers, meeting)
    livekit.available = False

    response = await client.delete(f"{MEETINGS}/{meeting['id']}", headers=headers)

    assert response.status_code == 204
