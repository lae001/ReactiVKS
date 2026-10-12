"""CLI работает со своей БД и коммитит по-настоящему, поэтому тесты удаляют созданные учетные записи сами."""

import asyncio
import io
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from auth_service import cli
from vks_common.db import create_engine

pytestmark = pytest.mark.integration

EMAIL = "cli-admin@example.ru"
PASSWORD = "correct-horse-7"


async def _query(database_url: str, sql: str) -> list[tuple[object, ...]]:
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            return [tuple(row) for row in (await connection.execute(text(sql), {"email": EMAIL})).all()]
    finally:
        await engine.dispose()


@pytest.fixture
def cli_environment(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AUTH_ARGON2_MEMORY_KIB", "8")
    monkeypatch.setenv("AUTH_ARGON2_TIME_COST", "1")
    yield database_url
    asyncio.run(_query(database_url, "DELETE FROM auth.users WHERE email = :email RETURNING id"))


def run(monkeypatch: pytest.MonkeyPatch, stdin: str, *arguments: str) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return cli.main(["create-admin", "--email", EMAIL, "--display-name", "Администратор", *arguments])


def test_create_admin_from_stdin(
    monkeypatch: pytest.MonkeyPatch, cli_environment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(monkeypatch, PASSWORD + "\n", "--password-stdin")

    rows = asyncio.run(_query(cli_environment, "SELECT role, status FROM auth.users WHERE email = :email"))
    assert code == 0
    assert rows == [("admin", "active")]
    assert "администратор создан" in capsys.readouterr().out


def test_existing_email_is_refused(
    monkeypatch: pytest.MonkeyPatch, cli_environment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, PASSWORD + "\n", "--password-stdin")

    code = run(monkeypatch, PASSWORD + "\n", "--password-stdin")

    assert code == 1
    assert "already registered" in capsys.readouterr().err


def test_weak_password_is_refused(
    monkeypatch: pytest.MonkeyPatch, cli_environment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(monkeypatch, "short\n", "--password-stdin")

    rows = asyncio.run(_query(cli_environment, "SELECT id FROM auth.users WHERE email = :email"))
    assert code == 1
    assert rows == []
    assert "at least 8" in capsys.readouterr().err


def test_mismatched_interactive_passwords_are_refused(
    monkeypatch: pytest.MonkeyPatch, cli_environment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, "different-password-1"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))

    code = run(monkeypatch, "")

    assert code == 1
    assert "не совпадают" in capsys.readouterr().err
