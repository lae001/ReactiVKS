from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vks_common.db import Database, constraint_name_of, create_engine, is_unique_violation, transaction
from vks_common.db.migrations import SchemaVersionMismatch, check_schema_is_current, load_alembic_config
from vks_common.testing import PostgresServer

pytestmark = pytest.mark.integration

EXAMPLE_ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


async def count_notes(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT count(*) FROM auth.notes"))
    return int(result.scalar_one())


async def test_service_role_cannot_touch_another_service_schema(postgres: PostgresServer) -> None:
    engine = create_engine(postgres.role_url("auth_svc"))

    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="permission denied for schema meeting"):
                await connection.execute(text("CREATE TABLE meeting.intruder (id int)"))
    finally:
        await engine.dispose()


async def test_citext_is_available_to_service_role(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 'Ivan@Example.RU'::citext = 'ivan@example.ru'::citext"))

    assert result.scalar_one() is True


async def test_transaction_commits_on_clean_exit(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, transaction(session):
        await session.execute(text("INSERT INTO auth.notes (title) VALUES ('committed')"))

    async with session_factory() as session:
        assert await count_notes(session) == 1


async def test_transaction_rolls_back_on_error(session_factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(RuntimeError):
        async with session_factory() as session, transaction(session):
            await session.execute(text("INSERT INTO auth.notes (title) VALUES ('lost')"))
            raise RuntimeError("сценарий упал")

    async with session_factory() as session:
        assert await count_notes(session) == 0


async def test_nested_transaction_joins_the_outer_one(session_factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(RuntimeError):
        async with session_factory() as session, transaction(session):
            async with transaction(session):
                await session.execute(text("INSERT INTO auth.notes (title) VALUES ('inner')"))
            raise RuntimeError("внешняя часть упала после внутренней")

    async with session_factory() as session:
        assert await count_notes(session) == 0


async def test_unique_violation_is_recognised_by_constraint_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await session.execute(text("INSERT INTO auth.notes (title) VALUES ('same')"))

        with pytest.raises(IntegrityError) as raised:
            await session.execute(text("INSERT INTO auth.notes (title) VALUES ('same')"))

    assert is_unique_violation(raised.value, constraint="notes_title_uk")
    assert not is_unique_violation(raised.value, constraint="other_uk")
    assert constraint_name_of(raised.value) == "notes_title_uk"


async def test_database_check_passes_against_live_server(engine: AsyncEngine) -> None:
    await Database(engine).check()


async def test_schema_check_passes_at_head(engine: AsyncEngine, auth_role_url: str) -> None:
    config = load_alembic_config(EXAMPLE_ALEMBIC_INI, database_url=auth_role_url)

    await check_schema_is_current(engine, config, schema="auth")


@pytest.fixture(scope="module")
def unmigrated_url(postgres: PostgresServer) -> str:
    """База, где миграции примера не применялись: в схеме нет alembic_version."""
    return postgres.role_url("auth_svc", database=postgres.create_database("chassis_unmigrated"))


async def test_schema_check_fails_where_migrations_were_not_applied(unmigrated_url: str) -> None:
    engine = create_engine(unmigrated_url)
    config = load_alembic_config(EXAMPLE_ALEMBIC_INI, database_url=unmigrated_url)

    try:
        with pytest.raises(SchemaVersionMismatch, match="<нет>"):
            await check_schema_is_current(engine, config, schema="auth")
    finally:
        await engine.dispose()


async def test_version_table_lives_in_service_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT version_num FROM auth.alembic_version"))

    assert result.scalar_one() == "0002"
