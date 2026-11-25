"""Тесты аналитики используют роль analytics_svc и настоящие миграции."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from analytics_service.settings import ALEMBIC_INI
from vks_common.testing import PostgresServer, apply_migrations, isolated_session_factory


@pytest.fixture(scope="session")
def database_url(postgres: PostgresServer) -> str:
    name = postgres.create_database("analytics_test")
    url = postgres.role_url("analytics_svc", database=name)
    apply_migrations(alembic_ini=ALEMBIC_INI, database_url=url)
    return url


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url)
    try:
        async with isolated_session_factory(engine) as factory:
            yield factory
    finally:
        await engine.dispose()
