"""Проверка границы смещений, согласий и REST-контракта рядов."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.domain.series import BufferedSample, Sample
from analytics_service.main import create_application
from analytics_service.services.projections import ProjectEvents
from analytics_service.services.series import FlushSamples
from analytics_service.settings import AnalyticsSettings
from vks_common.auth import use_authentication
from vks_common.clock import FixedClock
from vks_common.db import get_session
from vks_common.testing import TokenFactory, app_client
from vks_contracts import EventPayload, parse_event
from vks_contracts.envelope import envelope_for
from vks_contracts.meeting_events import ConsentChanged, MeetingStarted, ParticipantRegistered

pytestmark = pytest.mark.integration


async def project(sessions: async_sessionmaker[AsyncSession], payload: EventPayload, at: datetime) -> None:
    envelope = envelope_for(payload, event_id=uuid4(), occurred_at=at, producer="test")
    await ProjectEvents(sessions, FixedClock(at)).execute(parse_event(envelope.model_dump_json()))


async def test_contiguous_offset_and_weighted_series(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    meeting_id, owner_id, participant_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(seconds=20)
    await project(
        sessions,
        MeetingStarted(
            meeting_id=meeting_id,
            owner_id=owner_id,
            title="Демо",
            started_at=start,
            analysis_enabled=True,
            analysis_fps=3,
        ),
        start,
    )
    await project(
        sessions,
        ParticipantRegistered(
            meeting_id=meeting_id,
            participant_id=participant_id,
            display_name="Гость",
            role="guest",
            consent_state="granted",
        ),
        start,
    )
    old = now - timedelta(seconds=5)
    open_sample = now - timedelta(seconds=1)
    points = [
        BufferedSample(0, now, Sample(meeting_id, participant_id, old, (0, 0, 0, 1, 0, 0, 0), "demo")),
        BufferedSample(1, now, Sample(meeting_id, participant_id, open_sample, (0, 0, 0, 0, 0, 0, 1), "demo")),
        BufferedSample(2, now, Sample(meeting_id, participant_id, old, None, "demo")),
    ]
    flush = FlushSamples(sessions)

    assert (await flush.execute(0, points, now=now)).next_offset == 1
    assert (await flush.execute(0, points, now=now + timedelta(seconds=3))).next_offset == 3
    assert (await flush.execute(0, points, now=now + timedelta(seconds=3))).next_offset == 3
    revoke_at = now - timedelta(seconds=2)
    await project(
        sessions,
        ConsentChanged(
            meeting_id=meeting_id,
            participant_id=participant_id,
            consent_state="revoked",
            notice_version="test",
            decided_at=revoke_at,
        ),
        revoke_at,
    )
    invalid = BufferedSample(3, now, Sample(meeting_id, participant_id, open_sample, (0, 0, 0, 0, 0, 0, 1), "demo"))
    assert (await flush.execute(0, [invalid], now=now + timedelta(seconds=3))).next_offset == 4

    app = create_application(AnalyticsSettings(database_url=database_url))
    tokens = TokenFactory()
    use_authentication(app, tokens.verifier())

    async def isolated_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session
    path = f"/api/v1/reports/{meeting_id}/series"
    async with app_client(app) as client:
        headers = {"Authorization": f"Bearer {tokens.issue(user_id=owner_id)}"}
        response = await client.get(path, params={"resolution": "1s"}, headers=headers)
        other = await client.get(path, headers={"Authorization": f"Bearer {tokens.issue()}"})
        anonymous = await client.get(path)

    assert response.status_code == 200, response.text
    rows = response.json()["series"]
    assert len(rows) == 1
    assert rows[0]["participant_id"] == str(participant_id)
    assert len(rows[0]["points"]) == 1
    assert rows[0]["points"][0]["p"] == [0, 0, 0, 1, 0, 0, 0]
    assert rows[0]["points"][0]["face_ratio"] == 0.5
    assert other.status_code == 404
    assert anonymous.status_code == 401


async def test_migrations_are_reversible(database_url: str) -> None:
    import asyncio

    from analytics_service.settings import ALEMBIC_INI
    from vks_common.testing import apply_migrations, downgrade_migrations

    await asyncio.to_thread(downgrade_migrations, alembic_ini=ALEMBIC_INI, database_url=database_url)
    await asyncio.to_thread(apply_migrations, alembic_ini=ALEMBIC_INI, database_url=database_url)
