import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from auth_service.models import Base
from vks_common.db import constraint_name_of, sqlstate_of
from vks_common.db.errors import SQLSTATE_CHECK_VIOLATION
from vks_common.db.migrations import MIGRATION_CONNECT_ARGS, autogenerate_options
from vks_common.testing import apply_migrations, downgrade_migrations

pytestmark = pytest.mark.integration


async def insert_user(session: AsyncSession, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": uuid4(),
        "email": f"user-{uuid4().hex[:8]}@example.ru",
        "password_hash": "$argon2id$stub",
        "display_name": "Иван Петров",
    } | overrides
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    await session.execute(text(f"INSERT INTO auth.users ({columns}) VALUES ({placeholders})"), values)  # noqa: S608


async def test_migrations_are_reversible(alembic_ini: Path, database_url: str) -> None:
    await asyncio.to_thread(downgrade_migrations, alembic_ini=alembic_ini, database_url=database_url)
    await asyncio.to_thread(apply_migrations, alembic_ini=alembic_ini, database_url=database_url)


async def test_models_match_migrations(database_url: str) -> None:
    engine = create_async_engine(database_url, connect_args=MIGRATION_CONNECT_ARGS)

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(connection, opts=autogenerate_options("auth"))
        return list(compare_metadata(context, Base.metadata))

    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(diff)
    finally:
        await engine.dispose()

    assert differences == []


async def test_email_is_unique_regardless_of_case(session: AsyncSession) -> None:
    await insert_user(session, email="Ivan@Example.ru")

    with pytest.raises(IntegrityError) as raised:
        await insert_user(session, email="ivan@example.RU")

    assert constraint_name_of(raised.value) == "users_email_uk"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param({"email": "not-an-email"}, "users_email_ck", id="email-format"),
        pytest.param({"email": "a@" + "b" * 260}, "users_email_ck", id="email-length"),
        pytest.param({"display_name": ""}, "users_display_name_ck", id="empty-name"),
        pytest.param({"display_name": "x" * 101}, "users_display_name_ck", id="long-name"),
        pytest.param({"role": "guest"}, "users_role_ck", id="unknown-role"),
        pytest.param({"status": "deleted"}, "users_status_ck", id="unknown-status"),
    ],
)
async def test_check_constraints_guard_user_rows(
    session: AsyncSession, overrides: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError) as raised:
        await insert_user(session, **overrides)

    assert sqlstate_of(raised.value) == SQLSTATE_CHECK_VIOLATION
    assert constraint_name_of(raised.value) == constraint


async def test_new_user_is_active_organizer_by_default(session: AsyncSession) -> None:
    user_id = uuid4()

    await insert_user(session, id=user_id)

    row = (await session.execute(text("SELECT role, status FROM auth.users WHERE id = :id"), {"id": user_id})).one()
    assert tuple(row) == ("organizer", "active")


async def test_refresh_tokens_are_deleted_with_their_user(session: AsyncSession) -> None:
    user_id = uuid4()
    await insert_user(session, id=user_id)
    await session.execute(
        text(
            "INSERT INTO auth.refresh_tokens (id, user_id, family_id, token_hash, expires_at) "
            "VALUES (:id, :user_id, :family_id, :hash, now() + interval '30 days')"
        ),
        {"id": uuid4(), "user_id": user_id, "family_id": uuid4(), "hash": b"\x01" * 32},
    )

    await session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": user_id})

    remaining = await session.execute(
        text("SELECT count(*) FROM auth.refresh_tokens WHERE user_id = :id"), {"id": user_id}
    )
    assert remaining.scalar_one() == 0
