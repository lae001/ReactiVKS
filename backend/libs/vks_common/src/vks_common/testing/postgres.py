"""PostgreSQL для интеграционных тестов.

Контейнер поднимается тем же образом и тем же init-скриптом (``deploy/postgres/init``), что и в
``docker-compose.dev.yml``: роли и схемы сервисов в тестах настоящие, и тесты проверяют заодно права ролей. Схема
сервиса создается его настоящими миграциями – ``create_all`` не используется нигде.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import docker
from docker.errors import DockerException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

__all__ = [
    "POSTGRES_IMAGE",
    "SERVICE_ROLE_PASSWORDS",
    "PostgresServer",
    "docker_is_available",
    "find_init_scripts",
    "start_postgres",
]

# Тот же образ, что в docker-compose.dev.yml.
POSTGRES_IMAGE = "postgres:16-alpine"
DATABASE_NAME = "vks"
SUPERUSER = "postgres"
SUPERUSER_PASSWORD = "postgres-test-password"

# Роль сервиса → пароль. Переменные окружения init-скрипта называются по схеме: auth_svc → AUTH_DB_PASSWORD.
SERVICE_ROLE_PASSWORDS = {
    "auth_svc": "auth-test-password",
    "meeting_svc": "meeting-test-password",
    "analytics_svc": "analytics-test-password",
}


@dataclass(frozen=True, slots=True)
class PostgresServer:
    """Адрес запущенного PostgreSQL и учетные данные ролей."""

    host: str
    port: int

    def url(self, role: str, password: str, *, database: str = DATABASE_NAME) -> str:
        return f"postgresql+asyncpg://{role}:{password}@{self.host}:{self.port}/{database}"

    @property
    def superuser_url(self) -> str:
        return self.url(SUPERUSER, SUPERUSER_PASSWORD)

    def role_url(self, role: str, *, database: str = DATABASE_NAME) -> str:
        """Адрес для роли сервиса (``auth_svc``) – с ее правами, как у сервиса в работе."""
        return self.url(role, SERVICE_ROLE_PASSWORDS[role], database=database)

    def create_database(self, name: str) -> str:
        """Создать базу ``name`` копией ``vks`` после init-скрипта и вернуть ее имя.

        У каждого тестового пакета своя база: миграции разных пакетов (и их ``alembic_version``) не мешают друг
        другу, а роли, схемы и расширения те же, что в работе. ``CREATE DATABASE … TEMPLATE`` копирует их целиком.
        """
        asyncio.run(self._recreate(name))
        return name

    async def _recreate(self, name: str) -> None:
        engine = create_async_engine(self.superuser_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
                await connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE {DATABASE_NAME}'))
        finally:
            await engine.dispose()


def docker_is_available() -> bool:
    """Отвечает ли Docker. Без него интеграционные тесты пропускаются, а не падают."""
    try:
        docker.from_env().ping()
    except (DockerException, OSError):
        return False
    return True


def find_init_scripts(start: Path | None = None) -> Path:
    """Каталог ``deploy/postgres/init`` репозитория – ищется вверх от этого файла."""
    here = (start or Path(__file__)).resolve()
    for directory in here.parents:
        candidate = directory / "deploy" / "postgres" / "init"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("не найден deploy/postgres/init: тесты запускаются из репозитория ReactiVKS")


@contextmanager
def start_postgres() -> Iterator[PostgresServer]:
    """Запустить PostgreSQL с ролями и схемами сервисов и остановить по выходе.

    Ожидание готовности testcontainers подключается по TCP, а временный сервер init-скриптов слушает только
    unix-сокет, поэтому контейнер считается готовым уже после выполнения init-скрипта.
    """
    container = PostgresContainer(
        POSTGRES_IMAGE,
        username=SUPERUSER,
        password=SUPERUSER_PASSWORD,
        dbname=DATABASE_NAME,
        driver="asyncpg",
    )
    for role, password in SERVICE_ROLE_PASSWORDS.items():
        container.with_env(f"{role.removesuffix('_svc').upper()}_DB_PASSWORD", password)
    container.with_volume_mapping(str(find_init_scripts()), "/docker-entrypoint-initdb.d", "ro")
    with container:
        yield PostgresServer(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
        )
