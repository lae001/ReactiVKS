"""Точка входа meeting-service – корень сборки: здесь создаются адаптеры и кладутся туда, где их найдут роутеры.

uv run uvicorn meeting_service.main:create_application --factory --port 8002
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI

from meeting_service.adapters.livekit_server import LiveKitServerGateway
from meeting_service.api.v1 import join, meetings, participants
from meeting_service.settings import ALEMBIC_INI, MeetingSettings
from vks_common.app import HealthRegistry, create_app, use_database
from vks_common.auth import JwksKeys, TokenVerifier, use_authentication
from vks_common.clock import SystemClock
from vks_common.db import Database, create_engine_from_settings
from vks_common.db.migrations import check_schema_is_current, load_alembic_config

__all__ = ["create_application"]

SCHEMA = "meeting"


def create_application(settings: MeetingSettings | None = None) -> FastAPI:
    """Собрать приложение. ``settings`` – аргумент, чтобы тест собрал сервис без окружения."""
    resolved = settings or MeetingSettings.load()
    # Клиент JWKS создается при сборке: проверка токенов нужна каждому закрытому эндпоинту, а тесты подменяют
    # проверяющего целиком и до сети не доходят.
    jwks_client = httpx.AsyncClient(timeout=resolved.jwks_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(create_engine_from_settings(resolved))
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
        # Некритична: без LiveKit не войти во встречу, но список встреч и карточки работают.
        health.register("livekit", livekit.check, critical=False)
        try:
            yield
        finally:
            await livekit.aclose()
            await jwks_client.aclose()

    app = create_app(
        resolved,
        routers=[meetings.router, join.router, participants.router],
        lifespan=lifespan,
        title="ReactiVKS meeting-service",
    )
    app.state.clock = SystemClock()
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
