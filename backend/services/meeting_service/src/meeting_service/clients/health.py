"""Ограниченные по времени проверки компонентов без раскрытия секретов."""

import asyncio
from datetime import datetime, timedelta

import httpx

from meeting_service.domain.admin_health import ComponentStatus, HealthSnapshot
from meeting_service.settings import MeetingSettings
from vks_common.app import HealthRegistry
from vks_common.clock import Clock


async def read_health(
    settings: MeetingSettings,
    checks: HealthRegistry,
    client: httpx.AsyncClient,
    clock: Clock,
    heartbeat: datetime | None,
) -> HealthSnapshot:
    async def remote(url: str) -> ComponentStatus:
        try:
            response = await client.get(url + "/ready", timeout=2)
            response.raise_for_status()
            return ComponentStatus(
                status="ok" if all(v == "ok" for v in response.json().get("checks", {}).values()) else "degraded"
            )
        except (httpx.HTTPError, ValueError):
            return ComponentStatus(status="down")

    names = ["auth-service", "realtime-service", "analytics-service"]
    results = await asyncio.gather(
        *(
            remote(url)
            for url in (settings.auth_service_url, settings.realtime_service_url, settings.analytics_service_url)
        )
    )
    _, local = await checks.run(timeout_seconds=2)
    components = dict(zip(names, results, strict=True))
    components.update(
        {name: ComponentStatus(status="ok" if state == "ok" else "down") for name, state in local.items()}
    )
    components["meeting-service"] = ComponentStatus(status="ok")
    components["emotion-ml-service"] = ComponentStatus(
        status="ok" if heartbeat is not None and clock.now() - heartbeat < timedelta(seconds=10) else "down",
        last_heartbeat=heartbeat,
    )
    try:
        response = await client.get(settings.realtime_service_url + "/ready", timeout=2)
        redis = response.json().get("checks", {}).get("redis")
        components["redis"] = ComponentStatus(status="ok" if redis == "ok" else "down")
    except (httpx.HTTPError, ValueError):
        components["redis"] = ComponentStatus(status="down")
    return HealthSnapshot(
        status="ok" if all(c.status == "ok" for c in components.values()) else "degraded",
        checked_at=clock.now(),
        components=components,
    )
