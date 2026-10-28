import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from meeting_service.models import Base
from vks_common.db import constraint_name_of, sqlstate_of
from vks_common.db.errors import SQLSTATE_CHECK_VIOLATION
from vks_common.db.migrations import MIGRATION_CONNECT_ARGS, autogenerate_options
from vks_common.testing import apply_migrations, downgrade_migrations

pytestmark = pytest.mark.integration


async def insert(session: AsyncSession, table: str, values: dict[str, object]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    await session.execute(text(f"INSERT INTO meeting.{table} ({columns}) VALUES ({placeholders})"), values)  # noqa: S608


def invite_code() -> str:
    """Уникальный код из алфавита base32 в нижнем регистре: шестнадцатеричные цифры 0, 1, 8, 9 заменены буквами."""
    return uuid4().hex[:10].translate(str.maketrans("0189", "wxyz"))


async def insert_meeting(session: AsyncSession, **overrides: object) -> UUID:
    meeting_id = uuid4()
    values: dict[str, object] = {
        "id": meeting_id,
        "owner_id": uuid4(),
        "owner_name": "Иван Петров",
        "title": "Планерка",
        "invite_code": invite_code(),
        "analysis_enabled": True,
        "analysis_fps": 3,
    } | overrides
    await insert(session, "meetings", values)
    return meeting_id


async def insert_participant(session: AsyncSession, meeting_id: UUID, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": uuid4(),
        "meeting_id": meeting_id,
        "display_name": "Анна",
        "role": "guest",
        "consent_state": "granted",
        "participant_token_hash": uuid4().bytes + uuid4().bytes,
    } | overrides
    await insert(session, "participants", values)


async def test_migrations_are_reversible(alembic_ini: Path, database_url: str) -> None:
    await asyncio.to_thread(downgrade_migrations, alembic_ini=alembic_ini, database_url=database_url)
    await asyncio.to_thread(apply_migrations, alembic_ini=alembic_ini, database_url=database_url)


async def test_models_match_migrations(database_url: str) -> None:
    engine = create_async_engine(database_url, connect_args=MIGRATION_CONNECT_ARGS)

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(connection, opts=autogenerate_options("meeting"))
        return list(compare_metadata(context, Base.metadata))

    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(diff)
    finally:
        await engine.dispose()

    assert differences == []


async def test_new_meeting_is_scheduled(session: AsyncSession) -> None:
    meeting_id = await insert_meeting(session)

    status = await session.execute(text("SELECT status FROM meeting.meetings WHERE id = :id"), {"id": meeting_id})

    assert status.scalar_one() == "scheduled"


async def test_invite_code_is_unique(session: AsyncSession) -> None:
    await insert_meeting(session, invite_code="k3m7qx4tpa")

    with pytest.raises(IntegrityError) as raised:
        await insert_meeting(session, invite_code="k3m7qx4tpa")

    assert constraint_name_of(raised.value) == "meetings_invite_code_uk"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param({"invite_code": "K3M7QX4TPA"}, "meetings_invite_code_ck", id="invite-upper-case"),
        pytest.param({"invite_code": "k3m7qx4tp1"}, "meetings_invite_code_ck", id="invite-not-base32"),
        pytest.param({"title": ""}, "meetings_title_ck", id="empty-title"),
        pytest.param({"title": "x" * 201}, "meetings_title_ck", id="long-title"),
        pytest.param({"owner_name": ""}, "meetings_owner_name_ck", id="empty-owner-name"),
        pytest.param({"status": "paused"}, "meetings_status_ck", id="unknown-status"),
        pytest.param({"analysis_fps": 6}, "meetings_analysis_fps_ck", id="fps-too-high"),
        pytest.param({"status": "active"}, "meetings_started_at_ck", id="active-without-start"),
        pytest.param({"end_reason": "crash"}, "meetings_end_reason_ck", id="unknown-end-reason"),
    ],
)
async def test_check_constraints_guard_meeting_rows(
    session: AsyncSession, overrides: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError) as raised:
        await insert_meeting(session, **overrides)

    assert sqlstate_of(raised.value) == SQLSTATE_CHECK_VIOLATION
    assert constraint_name_of(raised.value) == constraint


async def test_ended_meeting_knows_when_it_ended(session: AsyncSession) -> None:
    started_at = await session.execute(text("SELECT now()"))

    with pytest.raises(IntegrityError) as raised:
        await insert_meeting(session, status="ended", started_at=started_at.scalar_one())

    assert constraint_name_of(raised.value) == "meetings_ended_at_ck"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"role": "organizer"}, id="organizer-with-token"),
        pytest.param({"user_id": uuid4()}, id="guest-with-account"),
        pytest.param({"participant_token_hash": None}, id="guest-without-token"),
    ],
)
async def test_participant_is_either_organizer_with_account_or_guest_with_token(
    session: AsyncSession, overrides: dict[str, object]
) -> None:
    meeting_id = await insert_meeting(session)

    with pytest.raises(IntegrityError) as raised:
        await insert_participant(session, meeting_id, **overrides)

    assert constraint_name_of(raised.value) == "participants_identity_ck"


async def test_organizer_is_one_participant_of_a_meeting(session: AsyncSession) -> None:
    meeting_id = await insert_meeting(session)
    organizer: dict[str, object] = {"role": "organizer", "user_id": uuid4(), "participant_token_hash": None}
    await insert_participant(session, meeting_id, **organizer)

    with pytest.raises(IntegrityError) as raised:
        await insert_participant(session, meeting_id, **organizer)

    assert constraint_name_of(raised.value) == "participants_meeting_id_user_id_uk"


async def test_participants_are_deleted_with_their_meeting(session: AsyncSession) -> None:
    meeting_id = await insert_meeting(session)
    await insert_participant(session, meeting_id)

    await session.execute(text("DELETE FROM meeting.meetings WHERE id = :id"), {"id": meeting_id})

    remaining = await session.execute(
        text("SELECT count(*) FROM meeting.participants WHERE meeting_id = :id"), {"id": meeting_id}
    )
    assert remaining.scalar_one() == 0


async def test_consent_log_outlives_its_meeting(session: AsyncSession) -> None:
    meeting_id = await insert_meeting(session)
    await insert(
        session,
        "consents",
        {
            "meeting_id": meeting_id,
            "participant_id": uuid4(),
            "display_name": "Анна",
            "meeting_title": "Планерка",
            "decision": "granted",
            "notice_version": "v1",
            "ip": "192.0.2.10",
        },
    )

    await session.execute(text("DELETE FROM meeting.meetings WHERE id = :id"), {"id": meeting_id})

    remaining = await session.execute(
        text("SELECT count(*) FROM meeting.consents WHERE meeting_id = :id"), {"id": meeting_id}
    )
    assert remaining.scalar_one() == 1


async def test_organizer_settings_default_to_analysis_on_at_3_fps(session: AsyncSession) -> None:
    user_id = uuid4()

    await insert(session, "organizer_settings", {"user_id": user_id})

    row = await session.execute(
        text(
            "SELECT analysis_enabled_default, analysis_fps_default FROM meeting.organizer_settings WHERE user_id = :id"
        ),
        {"id": user_id},
    )
    assert tuple(row.one()) == (True, 3)
