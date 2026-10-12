"""Изоляция тестов, работающих с БД.

Каждый тест получает фабрику сессий, привязанную к одному соединению с открытой транзакцией; сессии внутри нее
работают в точках сохранения. Код под тестом может коммитить, а внешний откат в конце теста убирает все.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vks_common.db.migrations import load_alembic_config

__all__ = ["apply_migrations", "downgrade_migrations", "isolated_session_factory"]


def apply_migrations(*, alembic_ini: Path | str, database_url: str, revision: str = "head") -> None:
    """Довести БД до ревизии настоящими миграциями.

    Синхронная: Alembic запускает свой цикл событий, поэтому вызывается из синхронной фикстуры уровня сессии или
    через ``asyncio.to_thread``.
    """
    command.upgrade(load_alembic_config(alembic_ini, database_url=database_url), revision)


def downgrade_migrations(*, alembic_ini: Path | str, database_url: str, revision: str = "base") -> None:
    """Откатить миграции до ревизии. Для теста обратимости миграций."""
    command.downgrade(load_alembic_config(alembic_ini, database_url=database_url), revision)


@asynccontextmanager
async def isolated_session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Фабрика сессий, чьи записи откатываются по окончании теста."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield factory
        finally:
            await outer.rollback()
