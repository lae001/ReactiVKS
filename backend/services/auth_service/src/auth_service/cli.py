"""Командная строка auth-service – корень сборки своего процесса, как ``main.py`` для HTTP.

    vks-auth create-admin --email admin@example.ru --display-name "Администратор"   # пароль спросит дважды
    echo "$ADMIN_PASSWORD" | vks-auth create-admin --email … --display-name … --password-stdin

Нужен только ``DATABASE_URL`` (и ``AUTH_ARGON2_*``, если стоимость хеша отличается от умолчаний): ключ подписи
команде не нужен.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.services.accounts import CreateAdmin
from auth_service.settings import PasswordHashingSettings
from vks_common.clock import SystemClock
from vks_common.config import ConfigurationError
from vks_common.db import Database, create_engine_from_settings
from vks_common.errors import AppError

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vks-auth", description="Администрирование auth-service")
    commands = parser.add_subparsers(dest="command", required=True)
    create_admin = commands.add_parser("create-admin", help="создать учетную запись администратора")
    create_admin.add_argument("--email", required=True)
    create_admin.add_argument("--display-name", required=True)
    create_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="прочитать пароль из стандартного ввода (для скриптов), а не спрашивать",
    )
    arguments = parser.parse_args(argv)

    try:
        password = _read_password(from_stdin=arguments.password_stdin)
        settings = PasswordHashingSettings.load()
    except (ValueError, ConfigurationError) as error:
        sys.stderr.write(f"ошибка: {error}\n")
        return 1
    return asyncio.run(
        _create_admin(settings, email=arguments.email, display_name=arguments.display_name, password=password)
    )


def _read_password(*, from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Пароль: ")
    if getpass.getpass("Пароль еще раз: ") != password:
        raise ValueError("пароли не совпадают")
    return password


async def _create_admin(settings: PasswordHashingSettings, *, email: str, display_name: str, password: str) -> int:
    database = Database(create_engine_from_settings(settings))
    hasher = Argon2Hasher(
        time_cost=settings.auth_argon2_time_cost,
        memory_kib=settings.auth_argon2_memory_kib,
        parallelism=settings.auth_argon2_parallelism,
    )
    try:
        async with database.session_factory() as session:
            user = await CreateAdmin(session=session, hasher=hasher, clock=SystemClock()).execute(
                email=email, password=password, display_name=display_name
            )
    except AppError as error:
        sys.stderr.write(f"ошибка: {error.detail}\n")
        return 1
    finally:
        await database.dispose()
    sys.stdout.write(f"администратор создан: {user.id}\n")
    return 0
