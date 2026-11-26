"""Один экземпляр задачи на период, освобождение блокировки и метрики ошибок."""

import asyncio
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

from vks_common.jobs import JobMetrics, run_periodic

pytestmark = pytest.mark.integration


async def test_job_lock_and_failure_recovery(engine: AsyncEngine) -> None:
    registry = CollectorRegistry()
    metrics = JobMetrics(registry)
    runs = 0
    called = asyncio.Event()
    job = "test-" + uuid4().hex

    async def callback() -> None:
        nonlocal runs
        runs += 1
        called.set()
        if runs == 1:
            raise ValueError("Transient test failure")

    first = asyncio.create_task(run_periodic(engine, job, callback, metrics, interval=0.2))
    second = asyncio.create_task(run_periodic(engine, job, callback, metrics, interval=0.2))
    try:
        await asyncio.wait_for(called.wait(), timeout=5)
        await asyncio.sleep(0.05)
        assert runs == 1
        await asyncio.sleep(0.4)
        assert runs >= 2
    finally:
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
    assert registry.get_sample_value("job_runs_total", {"job": job, "result": "error"}) == 1
    assert registry.get_sample_value("job_runs_total", {"job": job, "result": "ok"}) is not None
