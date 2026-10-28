"""Точка входа meeting-service – корень сборки: здесь создаются адаптеры и кладутся туда, где их найдут роутеры.

uv run uvicorn meeting_service.main:create_application --factory --port 8002
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI

from meeting_service.adapters.livekit_server import LiveKitServerGateway
from meeting_service.adapters.livekit_webhooks import LiveKitWebhookVerifier
from meeting_service.api import webhooks
from meeting_service.api.v1 import join, meetings, moderation, organizer_settings, participants
from meeting_service.consumers.user_events import UserEventsHandler
from meeting_service.models import OUTBOX
from meeting_service.settings import ALEMBIC_INI, MeetingSettings
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
from vks_common.logging import get_logger
from vks_contracts import Topic

__all__ = ["create_application"]

SCHEMA = "meeting"
# Группа потребителей meeting-service (events.md, «Группы потребителей»).
CONSUMER_GROUP = "meeting"

_logger = get_logger(__name__)


def create_application(settings: MeetingSettings | None = None) -> FastAPI:
    """Собрать приложение. ``settings`` – аргумент, чтобы тест собрал сервис без окружения."""
    resolved = settings or MeetingSettings.load()
    # Клиент JWKS создается при сборке: проверка токенов нужна каждому закрытому эндпоинту, а тесты подменяют
    # проверяющего целиком и до сети не доходят.
    jwks_client = httpx.AsyncClient(timeout=resolved.jwks_timeout_seconds)
    clock = SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        relay: OutboxRelay | None = None

        def wake_relay() -> None:
            if relay is not None:
                relay.notify()

        # Транзакция, записавшая событие в outbox, после фиксации будит релей – событие уходит сразу.
        database = Database(create_engine_from_settings(resolved), session_info={OUTBOX_NOTIFY: wake_relay})
        use_database(app, database)
        # До первого запроса: сервис на схеме не той версии пишет строки, которые следующий релиз не прочитает.
        await check_schema_is_current(database.engine, load_alembic_config(ALEMBIC_INI), schema=SCHEMA)
        # aiohttp-сессия шлюза создается внутри работающего цикла событий.
        livekit = LiveKitServerGateway(
            url=resolved.livekit_url,
            public_url=resolved.livekit_public_url,
            api_key=resolved.livekit_api_key,
            api_secret=resolved.livekit_api_secret.get_secret_value(),
            token_ttl=timedelta(seconds=resolved.livekit_token_ttl_seconds),
            timeout_seconds=resolved.livekit_timeout_seconds,
        )
        app.state.livekit = livekit
        health: HealthRegistry = app.state.health
        # Некритична: без LiveKit не войти во встречу, но история и карточки работают.
        health.register("livekit", livekit.check, critical=False)

        producer: EventProducer | None = None
        tasks: list[asyncio.Task[None]] = []
        if resolved.kafka_bootstrap_servers:
            producer = EventProducer(
                bootstrap_servers=resolved.kafka_bootstrap_servers, client_id=resolved.service_name
            )
            relay = OutboxRelay(
                session_factory=database.session_factory,
                table=OUTBOX,
                producer=producer,
                clock=clock,
                poll_interval_seconds=resolved.outbox_poll_interval_seconds,
            )
            # Некритична (conventions.md, §10): пока брокер недоступен, события копятся в outbox.
            health.register("kafka", producer.check, critical=False)
            # user.events с начала: проекция блокировок строится по всей истории топика.
            consumer = EventConsumer(
                bootstrap_servers=resolved.kafka_bootstrap_servers,
                topics=[Topic.USER_EVENTS],
                group_id=CONSUMER_GROUP,
                client_id=resolved.service_name,
                handler=UserEventsHandler(session_factory=database.session_factory, clock=clock, livekit=livekit),
                dead_letters=producer,
                clock=clock,
                auto_offset_reset="earliest",
            )
            tasks = [
                asyncio.create_task(run_outbox_relay(producer, relay), name="outbox-relay"),
                asyncio.create_task(run_consumer(consumer), name="user-events-consumer"),
            ]
            for task in tasks:
                task.add_done_callback(log_unexpected_stop)
        else:
            _logger.warning("kafka is not configured: events stay in outbox")
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if producer is not None:
                await producer.stop()
            await livekit.aclose()
            await jwks_client.aclose()

    app = create_app(
        resolved,
        routers=[
            meetings.router,
            moderation.router,
            join.router,
            participants.router,
            organizer_settings.router,
            webhooks.router,
        ],
        lifespan=lifespan,
        title="ReactiVKS meeting-service",
    )
    app.state.clock = clock
    # Проверка подписи вебхуков локальная, без сети: создается при сборке, а не в lifespan.
    app.state.webhook_verifier = LiveKitWebhookVerifier(
        api_key=resolved.livekit_api_key, api_secret=resolved.livekit_api_secret.get_secret_value()
    )
    use_authentication(
        app,
        TokenVerifier(
            keys=JwksKeys(resolved.jwks_url, http_client=jwks_client),
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            leeway_seconds=resolved.jwt_leeway_seconds,
        ),
    )
    return app
