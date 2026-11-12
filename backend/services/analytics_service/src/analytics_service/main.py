"""Корень сборки analytics-service."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from analytics_service.api.reports import router
from analytics_service.consumers.samples import SampleConsumer
from analytics_service.models import OUTBOX
from analytics_service.services.projections import ProjectEvents
from analytics_service.services.reports import BuildReports
from analytics_service.services.series import FlushSamples
from analytics_service.settings import ALEMBIC_INI, AnalyticsSettings
from analytics_service.workers.reports import run_reports
from vks_common.app import HealthRegistry, create_app, use_database
from vks_common.auth import JwksKeys, TokenVerifier, use_authentication
from vks_common.clock import SystemClock
from vks_common.db import Database, create_engine_from_settings
from vks_common.db.migrations import check_schema_is_current, load_alembic_config
from vks_common.kafka import (
    OUTBOX_NOTIFY,
    EventConsumer,
    EventProducer,
    OutboxRelay,
    log_unexpected_stop,
    run_consumer,
    run_outbox_relay,
)
from vks_contracts import Topic


def create_application(settings: AnalyticsSettings | None = None) -> FastAPI:
    resolved = settings or AnalyticsSettings.load()
    jwks = httpx.AsyncClient(timeout=2.0)
    clock = SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        relay: OutboxRelay | None = None

        def wake_relay() -> None:
            if relay is not None:
                relay.notify()

        database = Database(create_engine_from_settings(resolved), session_info={OUTBOX_NOTIFY: wake_relay})
        use_database(app, database)
        await check_schema_is_current(database.engine, load_alembic_config(ALEMBIC_INI), schema="analytics")
        producer = EventProducer(bootstrap_servers=resolved.kafka_bootstrap_servers, client_id=resolved.service_name)
        relay = OutboxRelay(session_factory=database.session_factory, table=OUTBOX, producer=producer, clock=clock)
        health: HealthRegistry = app.state.health
        health.register("kafka", producer.check, critical=False)
        projections = EventConsumer(
            bootstrap_servers=resolved.kafka_bootstrap_servers,
            topics=[Topic.MEETING_EVENTS, Topic.USER_EVENTS],
            group_id="analytics-projections",
            client_id=resolved.service_name,
            handler=ProjectEvents(database.session_factory, clock).execute,
            dead_letters=producer,
            clock=clock,
        )
        samples = SampleConsumer(
            bootstrap_servers=resolved.kafka_bootstrap_servers,
            flush=FlushSamples(database.session_factory),
            clock=clock,
        )
        reports = BuildReports(
            database.session_factory, clock, samples.watermark, shift_threshold=resolved.report_shift_threshold
        )
        tasks = [
            asyncio.create_task(run_reports(reports), name="analytics-reports"),
            asyncio.create_task(run_outbox_relay(producer, relay), name="analytics-outbox"),
            asyncio.create_task(run_consumer(projections), name="analytics-projections"),
            asyncio.create_task(samples.run(), name="analytics-samples"),
        ]
        for task in tasks:
            task.add_done_callback(log_unexpected_stop)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await producer.stop()
            await jwks.aclose()

    app = create_app(resolved, routers=[router], lifespan=lifespan, title="ReactiVKS analytics-service")
    use_authentication(
        app,
        TokenVerifier(
            keys=JwksKeys(resolved.jwks_url, http_client=jwks),
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            leeway_seconds=resolved.jwt_leeway_seconds,
        ),
    )
    return app
