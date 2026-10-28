"""Изоляция схем сервисов (ADR-004, database.md): роль видит и меняет только свою схему.

Права выдает init-скрипт ``deploy/postgres/init``, которым создан тестовый PostgreSQL, – проверяются настоящие роли.
"""

from collections.abc import AsyncIterator, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from vks_common.db import create_engine, sqlstate_of
from vks_common.testing import PostgresServer

pytestmark = pytest.mark.integration

SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501"

EngineFor = Callable[[str], AsyncEngine]


@pytest.fixture
async def engine_for(postgres: PostgresServer, database_url: str) -> AsyncIterator[EngineFor]:
    """Движок под ролью сервиса к базе тестов meeting-service, где схема meeting уже создана миграциями."""
    database = database_url.rsplit("/", 1)[1]
    engines: list[AsyncEngine] = []

    def make(role: str) -> AsyncEngine:
        engine = create_engine(postgres.role_url(role, database=database), pool_size=1, max_overflow=0)
        engines.append(engine)
        return engine

    yield make
    for engine in engines:
        await engine.dispose()


async def assert_denied(connection: AsyncConnection, statement: str) -> None:
    with pytest.raises(DBAPIError) as raised:
        await connection.execute(text(statement))

    assert sqlstate_of(raised.value) == SQLSTATE_INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize("role", ["auth_svc", "analytics_svc"])
async def test_other_services_cannot_read_meeting_schema(engine_for: EngineFor, role: str) -> None:
    async with engine_for(role).connect() as connection:
        await assert_denied(connection, "SELECT count(*) FROM meeting.meetings")


@pytest.mark.parametrize("schema", ["auth", "analytics", "public"])
async def test_meeting_service_cannot_create_tables_outside_its_schema(engine_for: EngineFor, schema: str) -> None:
    async with engine_for("meeting_svc").connect() as connection:
        await assert_denied(connection, f"CREATE TABLE {schema}.intruder (id int)")


async def test_meeting_service_owns_its_schema(engine_for: EngineFor) -> None:
    async with engine_for("meeting_svc").connect() as connection:
        owner = await connection.execute(
            text("SELECT nspowner::regrole::text FROM pg_namespace WHERE nspname = 'meeting'")
        )

        assert owner.scalar_one() == "meeting_svc"
