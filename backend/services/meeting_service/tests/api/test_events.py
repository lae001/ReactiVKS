"""События meeting.events пишутся в outbox той же транзакцией, что и изменение (ADR-011), и проходят контракт."""

import json
from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import CURRENT_NOTICE
from vks_contracts import parse_event
from vks_contracts.meeting_events import MeetingEnded, MeetingStarted, ParticipantRegistered

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


async def outbox(session: AsyncSession, meeting_id: str) -> list[tuple[str, str, str, dict[str, object]]]:
    rows = await session.execute(
        text("SELECT topic, event_key, event_type, envelope FROM meeting.outbox WHERE event_key = :key ORDER BY id"),
        {"key": meeting_id},
    )
    return [tuple(row) for row in rows]


async def test_meeting_lifecycle_is_published_in_order(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, session: AsyncSession
) -> None:
    headers = organizer_headers(uuid4(), name="Иван Петров")
    meeting = (await client.post(MEETINGS, json={"title": "Планерка"}, headers=headers)).json()
    await client.post(f"{MEETINGS}/{meeting['id']}/join", json={"consent": "granted"}, headers=headers)
    await client.post(
        f"/api/v1/join/{meeting['invite_code']}",
        json={"display_name": "Анна", "consent": "denied", "notice_version": CURRENT_NOTICE.version},
    )
    await client.post(f"{MEETINGS}/{meeting['id']}/join", json={"consent": "denied"}, headers=headers)
    await client.post(f"{MEETINGS}/{meeting['id']}/end", headers=headers)

    rows = await outbox(session, meeting["id"])

    assert [event_type for _, _, event_type, _ in rows] == [
        "meeting.created",
        "meeting.started",
        "participant.registered",
        "participant.registered",
        "consent.changed",
        "meeting.ended",
    ]
    assert {topic for topic, _, _, _ in rows} == {"meeting.events"}
    events = [parse_event(json.dumps(envelope)) for _, _, _, envelope in rows]
    assert all(event.envelope.producer == "meeting-service" for event in events)
    started, guest, ended = events[1].payload, events[3].payload, events[5].payload
    assert isinstance(started, MeetingStarted)
    assert started.analysis_fps == 3
    assert isinstance(guest, ParticipantRegistered)
    assert (guest.display_name, guest.role, guest.consent_state) == ("Анна", "guest", "denied")
    assert isinstance(ended, MeetingEnded)
    assert ended.reason == "organizer"


async def test_failed_join_publishes_nothing(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, session: AsyncSession
) -> None:
    headers = organizer_headers(uuid4())
    meeting = (await client.post(MEETINGS, json={"title": "Планерка"}, headers=headers)).json()

    await client.post(f"{MEETINGS}/{meeting['id']}/join", headers=headers)  # без согласия – 409

    assert [event_type for _, _, event_type, _ in await outbox(session, meeting["id"])] == ["meeting.created"]
