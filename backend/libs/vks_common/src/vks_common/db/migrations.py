"""Миграции Alembic: конфигурация, окружение ``env.py`` и сверка версии схемы при старте.

``alembic_version`` каждого сервиса живет в его схеме (database.md), поэтому все функции здесь принимают схему.
Адрес БД берется из ``DATABASE_URL`` (или ``DATABASE_URL_FILE``), а не из ``alembic.ini``: файл в git, пароль – нет.

``migrations/env.py`` сервиса – три строки::

    from auth_service.models import Base
    from vks_common.db.migrations import run_migrations

    run_migrations(target_metadata=Base.metadata, schema="auth")
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import context
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from vks_common.config import DatabaseServiceSettings
from vks_common.logging import get_logger

__all__ = [
    "MIGRATION_CONNECT_ARGS",
    "SchemaVersionMismatch",
    "autogenerate_options",
    "check_schema_is_current",
    "current_revisions",
    "head_revisions",
    "load_alembic_config",
    "run_migrations",
]

_logger = get_logger(__name__)


class SchemaVersionMismatch(RuntimeError):
    """Схема БД не та, под которую написан код."""


class _MigrationSettings(DatabaseServiceSettings):
    """Единственное, что нужно запуску миграций, – адрес БД."""

    service_name: str = "migrations"


def load_alembic_config(alembic_ini: Path | str, *, database_url: str | None = None) -> Config:
    """Прочитать ``alembic.ini`` сервиса.

    ``script_location`` в файле указан относительно него и делается абсолютным: тесты и запуск при старте работают
    из других каталогов.
    """
    path = Path(alembic_ini).resolve()
    config = Config(str(path))
    script_location = config.get_main_option("script_location")
    if script_location is not None and not Path(script_location).is_absolute():
        config.set_main_option("script_location", str(path.parent / script_location))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_migrations(*, target_metadata: MetaData, schema: str) -> None:
    """Выполнить миграции так, как вызван Alembic: в режиме SQL (``--sql``) или против БД."""
    url = context.config.get_main_option("sqlalchemy.url") or _MigrationSettings.load().database_url_value
    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=target_metadata,
            version_table_schema=schema,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    asyncio.run(_run_online(url, target_metadata, schema))


async def _run_online(url: str, target_metadata: MetaData, schema: str) -> None:
    # NullPool: запуск миграций – одно соединение на несколько секунд, держать пул незачем.
    engine = create_async_engine(url, poolclass=NullPool, connect_args=MIGRATION_CONNECT_ARGS)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_apply, target_metadata, schema)
    finally:
        await engine.dispose()


# Соединения миграций работают с search_path = public. У роли сервиса схема по умолчанию – его собственная
# (search_path = auth, public), и тогда Alembic отражает ее таблицы и внешние ключи без схемы, а модели объявляют
# схему явно: сравнение видело бы расхождения там, где их нет. Так схема сервиса всегда названа явно – и в
# миграциях, и в отражении.
MIGRATION_CONNECT_ARGS: dict[str, object] = {"server_settings": {"search_path": "public"}}


def autogenerate_options(schema: str) -> dict[str, object]:
    """Параметры сравнения моделей с БД – общие для ``env.py`` и теста «модели = миграции».

    Сравнивается только схема сервиса: чужие ему не принадлежат.
    """

    def include_name(name: str | None, type_: str, parent_names: object) -> bool:
        return type_ != "schema" or name == schema

    return {
        # alembic_version – в схеме сервиса (database.md), и сравнение не должно считать ее лишней таблицей.
        "version_table_schema": schema,
        "include_schemas": True,
        "include_name": include_name,
        # Без compare_type изменение типа колонки автогенерация молча пропускает.
        "compare_type": True,
        "compare_server_default": True,
    }


def _apply(connection: Connection, target_metadata: MetaData, schema: str) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        **autogenerate_options(schema),  # type: ignore[arg-type]  # configure принимает **kw без типов
    )
    with context.begin_transaction():
        context.run_migrations()


def head_revisions(config: Config) -> set[str]:
    """Ревизии, которыми заканчиваются миграции сервиса."""
    return set(ScriptDirectory.from_config(config).get_heads())


async def current_revisions(engine: AsyncEngine, *, schema: str) -> set[str]:
    """Ревизии, на которых стоит БД; пусто, если миграции не применялись."""

    def read(connection: Connection) -> set[str]:
        migration_context = MigrationContext.configure(connection, opts={"version_table_schema": schema})
        return set(migration_context.get_current_heads())

    async with engine.connect() as connection:
        return await connection.run_sync(read)


async def check_schema_is_current(engine: AsyncEngine, config: Config, *, schema: str) -> None:
    """Не дать сервису стартовать на схеме не той версии.

    Работа на чужой версии схемы тихо портит данные, а упавший при старте сервис оператор видит сразу.
    """
    expected = head_revisions(config)
    actual = await current_revisions(engine, schema=schema)
    if actual == expected:
        _logger.info("database schema is current", revision=sorted(actual))
        return
    raise SchemaVersionMismatch(
        f"схема {schema} не совпадает с кодом: миграции заканчиваются на {sorted(expected) or ['<нет>']}, "
        f"БД стоит на {sorted(actual) or ['<нет>']}. Выполните 'alembic upgrade head'."
    )
