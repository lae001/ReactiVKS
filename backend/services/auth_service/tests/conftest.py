"""Фикстуры тестов auth-service.

Схема ``auth`` создается настоящими миграциями под ролью ``auth_svc`` – с теми же правами, что у сервиса в работе.
Каждый тест работает в транзакции, которая откатывается по его окончании.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vks_common.db import create_engine
from vks_common.testing import PostgresServer, apply_migrations, isolated_session_factory

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def alembic_ini() -> Path:
    return ALEMBIC_INI


@pytest.fixture(scope="session")
def database_url(postgres: PostgresServer) -> str:
    """Адрес роли auth_svc; схема auth доведена до головы миграций."""
    url = postgres.role_url("auth_svc", database=postgres.create_database("auth_test"))
    apply_migrations(alembic_ini=ALEMBIC_INI, database_url=url)
    return url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url, pool_size=2, max_overflow=2)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with isolated_session_factory(engine) as factory:
        yield factory


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
