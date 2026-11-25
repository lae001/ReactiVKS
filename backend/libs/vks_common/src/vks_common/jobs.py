"""Периодические задачи с PostgreSQL-блокировкой на цикл и ограниченным временем работы."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from time import monotonic

from prometheus_client import CollectorRegistry, Counter, Histogram
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from vks_common.logging import get_logger

_logger = get_logger(__name__)


class JobMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.runs = Counter("job_runs_total", "Background job outcomes", ["job", "result"], registry=registry)
        self.duration = Histogram("job_duration_seconds", "Background job duration", ["job"], registry=registry)


async def run_periodic(
    engine: AsyncEngine,
    name: str,
    callback: Callable[[], Awaitable[None]],
    metrics: JobMetrics,
    *,
    interval: float = 60,
    timeout_seconds: float = 30,
) -> None:
    key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], signed=True)
    while True:
        try:
            async with engine.connect() as connection:
                locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
                await connection.commit()
                if locked:
                    try:
                        started = monotonic()
                        try:
                            async with asyncio.timeout(timeout_seconds):
                                await callback()
                        except Exception:  # noqa: BLE001 - сбой задачи не останавливает расписание
                            metrics.runs.labels(name, "error").inc()
                            _logger.exception("background job failed", job=name)
                        else:
                            metrics.runs.labels(name, "ok").inc()
                        finally:
                            metrics.duration.labels(name).observe(monotonic() - started)
                        await asyncio.sleep(interval)
                    finally:
                        await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                        await connection.commit()
                else:
                    await asyncio.sleep(min(interval, 5))
        except Exception:  # noqa: BLE001 - переподключение при отказе PostgreSQL
            _logger.exception("job lock failed", job=name)
            await asyncio.sleep(5)
