"""Отчет ждет записанных отсчетов и публикуется один раз."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.domain.report_jobs import SampleWatermark
from analytics_service.domain.series import BufferedSample, Sample
from analytics_service.main import create_application
from analytics_service.services.projections import ProjectEvents
from analytics_service.services.reports import BuildReports
from analytics_service.services.series import FlushSamples
from analytics_service.settings import AnalyticsSettings
from vks_common.auth import use_authentication
from vks_common.clock import FixedClock
from vks_common.db import get_session
from vks_common.testing import TokenFactory, app_client
from vks_contracts.envelope import envelope_for
from vks_contracts.meeting_events import MeetingEnded, MeetingStarted, ParticipantRegistered
from vks_contracts.registry import parse_event

pytestmark = pytest.mark.integration


async def test_report_waits_for_watermark_and_publishes_once(
    sessions: async_sessionmaker[AsyncSession],
    database_url: str,
) -> None:
    owner, meeting_id, participant_id = uuid4(), uuid4(), uuid4()
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    end = start + timedelta(seconds=45)
    clock = FixedClock(end + timedelta(seconds=6))
    events = [
        (
            start,
            MeetingStarted(
                meeting_id=meeting_id,
                owner_id=owner,
                title="Разбор",
                started_at=start,
                analysis_enabled=True,
                analysis_fps=3,
            ),
        ),
        (
            start,
            ParticipantRegistered(
                meeting_id=meeting_id,
                participant_id=participant_id,
                display_name="Гость",
                role="guest",
                consent_state="granted",
            ),
        ),
        (end, MeetingEnded(meeting_id=meeting_id, ended_at=end, reason="organizer")),
    ]
    for at, event in events:
        envelope = envelope_for(event, event_id=uuid4(), occurred_at=at, producer="test")
        await ProjectEvents(sessions, FixedClock(end)).execute(parse_event(envelope.model_dump_json()))

    async def watermark(_: UUID) -> SampleWatermark:
        return 0, 46

    flush = FlushSamples(sessions)
    points = [
        BufferedSample(
            i,
            clock.now(),
            Sample(
                meeting_id,
                participant_id,
                start + timedelta(seconds=i),
                (0, 0, 0, 1, 0, 0, 0) if i < 30 else (0, 0, 0, 0, 1, 0, 0),
                "test",
            ),
        )
        for i in range(45)
    ]
    await flush.execute(0, points, now=clock.now())
    app = create_application(AnalyticsSettings(database_url=database_url))
    tokens = TokenFactory()
    use_authentication(app, tokens.verifier())

    async def session() -> AsyncIterator[AsyncSession]:
        async with sessions() as isolated:
            yield isolated

    app.dependency_overrides[get_session] = session
    builder = BuildReports(sessions, clock, watermark, shift_threshold=0.3)
    path = f"/api/v1/reports/{meeting_id}"
    headers = {"Authorization": f"Bearer {tokens.issue(user_id=owner)}"}
    async with app_client(app) as client:
        await builder.execute()
        pending = await client.get(path, headers=headers)
        await flush.execute(0, [BufferedSample(45, clock.now(), None)], now=clock.now())
        await builder.execute()
        await builder.execute()
        ready = await client.get(path, headers=headers)
        other = await client.get(path, headers={"Authorization": f"Bearer {tokens.issue()}"})

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert "summary" not in pending.json()
    assert ready.status_code == 200, ready.text
    report = ready.json()
    assert report["status"] == "ready"
    assert report["model_version"] == "test"
    assert report["meeting"]["duration_s"] == 45
    assert report["summary"]["participants"][0]["analyzed_seconds"] == 45
    assert report["summary"]["overall"]["distribution"]["sad"] == pytest.approx(1 / 3)
    assert {marker["participant_id"] for marker in report["markers"]} == {str(participant_id), None}
    assert other.status_code == 404
    async with sessions() as query:
        rows = await query.scalars(
            text("SELECT event_type FROM analytics.outbox WHERE event_key = :key"), {"key": str(meeting_id)}
        )
        assert rows.all() == ["report.ready"]
