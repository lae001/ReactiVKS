"""Точка входа auth-service – корень сборки: здесь создаются адаптеры и кладутся туда, где их найдут роутеры.

uv run uvicorn auth_service.main:create_application --factory --port 8001
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.adapters.rsa_keys import RsaKeyRing
from auth_service.api.v1 import admin, auth, users
from auth_service.models import OUTBOX
from auth_service.settings import ALEMBIC_INI, AuthSettings
from vks_common.app import HealthRegistry, create_app, use_database
from vks_common.auth import StaticKeys, TokenVerifier, use_authentication
from vks_common.clock import SystemClock
from vks_common.db import Database, create_engine_from_settings
from vks_common.db.migrations import check_schema_is_current, load_alembic_config
from vks_common.kafka import OUTBOX_NOTIFY, EventProducer, OutboxRelay, log_unexpected_stop, run_outbox_relay
from vks_common.logging import get_logger

__all__ = ["create_application"]

SCHEMA = "auth"

_logger = get_logger(__name__)


def create_application(settings: AuthSettings | None = None) -> FastAPI:
    """Собрать приложение. ``settings`` – аргумент, чтобы тест собрал сервис без окружения."""
    resolved = settings or AuthSettings.load()
    # Ключ и хешер создаются при сборке, а не в lifespan: нечитаемый ключ останавливает процесс сразу, а тесты
    # получают рабочее приложение без запуска lifespan.
    key_ring = RsaKeyRing(
        resolved.read_private_key_pem(),
        previous_public_key_pem=resolved.read_previous_public_key_pem(),
    )

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

        producer: EventProducer | None = None
        relay_task: asyncio.Task[None] | None = None
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
            health: HealthRegistry = app.state.health
            # Некритична (conventions.md, §10): пока брокер недоступен, события копятся в outbox.
            health.register("kafka", producer.check, critical=False)
            relay_task = asyncio.create_task(run_outbox_relay(producer, relay), name="outbox-relay")
            relay_task.add_done_callback(log_unexpected_stop)
        else:
            _logger.warning("kafka is not configured: events stay in outbox")
        try:
            yield
        finally:
            if relay_task is not None:
                relay_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await relay_task
            if producer is not None:
                await producer.stop()

    app = create_app(
        resolved,
        routers=[auth.router, users.router, admin.router],
        lifespan=lifespan,
        title="ReactiVKS auth-service",
    )
    app.state.password_hasher = Argon2Hasher(
        time_cost=resolved.auth_argon2_time_cost,
        memory_kib=resolved.auth_argon2_memory_kib,
        parallelism=resolved.auth_argon2_parallelism,
    )
    app.state.token_signer = key_ring
    app.state.clock = clock
    # Свои токены auth-service проверяет своими же публичными ключами, без HTTP-запроса к собственному JWKS.
    use_authentication(
        app,
        TokenVerifier(
            keys=StaticKeys(key_ring.verification_keys()),
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            leeway_seconds=resolved.jwt_leeway_seconds,
        ),
    )
    return app
