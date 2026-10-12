"""Фикстуры тестов шасси.

PostgreSQL поднимается один раз на сессию тем же init-скриптом, что и в docker-compose.dev.yml. Тестам, которым не
нужен Docker, эти фикстуры не мешают: контейнер стартует только при первом запросе фикстуры.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vks_common.db import create_engine
from vks_common.testing import PostgresServer, apply_migrations, isolated_session_factory

EXAMPLE_ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


@pytest.fixture(scope="session")
def auth_role_url(postgres: PostgresServer) -> str:
    """Адрес роли auth_svc, схема auth доведена до головы миграций примера."""
    url = postgres.role_url("auth_svc", database=postgres.create_database("chassis_test"))
    apply_migrations(alembic_ini=EXAMPLE_ALEMBIC_INI, database_url=url)
    return url


@pytest.fixture
async def engine(auth_role_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(auth_role_url, pool_size=2, max_overflow=2)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with isolated_session_factory(engine) as factory:
        yield factory
