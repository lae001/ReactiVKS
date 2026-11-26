"""Сводка не скрывает отказы зависимостей; heartbeat устаревает."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from meeting_service.clients.health import read_health
from meeting_service.consumers.ml_status import MlHeartbeat
from meeting_service.settings import MeetingSettings
from vks_common.app import HealthRegistry
from vks_common.clock import FixedClock
from vks_contracts import envelope_for, parse_event
from vks_contracts.ml_events import MlStatus


@pytest.mark.parametrize("available", [True, False])
async def test_health_reports_failures(available: bool) -> None:
    settings = MeetingSettings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        livekit_api_key="test",
        livekit_api_secret="x" * 32,
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if available else 503, json={"checks": {"redis": "ok"}})

    clock = FixedClock(datetime.now(UTC))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        health = await read_health(settings, HealthRegistry(), client, clock, clock.now())
        assert health.components["emotion-ml-service"].status == "ok"
        assert health.status == ("ok" if available else "degraded")
        old = await read_health(settings, HealthRegistry(), client, clock, clock.now() - timedelta(seconds=11))
        assert old.components["emotion-ml-service"].status == "down"


async def test_old_heartbeat_does_not_replace_new() -> None:
    heartbeat = MlHeartbeat()
    now = datetime.now(UTC)
    payload = MlStatus(meeting_id=uuid4(), state="active", effective_fps=3, target_fps=3, worker_id="test")
    for at in (now, now - timedelta(minutes=1)):
        event = envelope_for(payload, event_id=uuid4(), occurred_at=at, producer="test")
        await heartbeat.execute(parse_event(event.model_dump_json()))
    assert heartbeat.latest == now
