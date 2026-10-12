"""Точка входа auth-service – корень сборки: здесь создаются адаптеры и кладутся туда, где их найдут роутеры.

uv run uvicorn auth_service.main:create_application --factory --port 8001
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.adapters.rsa_keys import RsaKeyRing
from auth_service.api.v1 import auth, users
from auth_service.settings import ALEMBIC_INI, AuthSettings
from vks_common.app import create_app, use_database
from vks_common.auth import StaticKeys, TokenVerifier, use_authentication
from vks_common.clock import SystemClock
from vks_common.db import Database, create_engine_from_settings
from vks_common.db.migrations import check_schema_is_current, load_alembic_config

__all__ = ["create_application"]

SCHEMA = "auth"


def create_application(settings: AuthSettings | None = None) -> FastAPI:
    """Собрать приложение. ``settings`` – аргумент, чтобы тест собрал сервис без окружения."""
    resolved = settings or AuthSettings.load()
    # Ключ и хешер создаются при сборке, а не в lifespan: нечитаемый ключ останавливает процесс сразу, а тесты
    # получают рабочее приложение без запуска lifespan.
    key_ring = RsaKeyRing(
        resolved.read_private_key_pem(),
        previous_public_key_pem=resolved.read_previous_public_key_pem(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(create_engine_from_settings(resolved))
        use_database(app, database)
        # До первого запроса: сервис на схеме не той версии пишет строки, которые следующий релиз не прочитает.
        await check_schema_is_current(database.engine, load_alembic_config(ALEMBIC_INI), schema=SCHEMA)
        yield

    app = create_app(resolved, routers=[auth.router, users.router], lifespan=lifespan, title="ReactiVKS auth-service")
    app.state.password_hasher = Argon2Hasher(
        time_cost=resolved.auth_argon2_time_cost,
        memory_kib=resolved.auth_argon2_memory_kib,
        parallelism=resolved.auth_argon2_parallelism,
    )
    app.state.token_signer = key_ring
    app.state.clock = SystemClock()
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
