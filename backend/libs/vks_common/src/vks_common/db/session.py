"""Сессии и транзакции.

Границы транзакции принадлежат сценарию: репозиторий никогда не коммитит, иначе изменение и запись в outbox нельзя
объединить в одну транзакцию.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import Request

__all__ = ["Database", "create_session_factory", "get_database", "get_session", "transaction"]


def create_session_factory(
    engine: AsyncEngine, *, info: Mapping[str, object] | None = None
) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий сервиса.

    ``expire_on_commit=False``: прочитанные атрибуты остаются доступны после коммита – репозиторий преобразует
    строку в доменную сущность, когда транзакция уже закрыта. ``info`` копируется в ``session.info`` каждой сессии –
    так outbox находит, кого разбудить после фиксации (``vks_common.kafka.OUTBOX_NOTIFY``).
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        info=dict(info) if info else None,
    )


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Выполнить блок в транзакции; если она уже открыта – присоединиться к ней.

    Вложенный вызов не открывает вторую транзакцию: сценарий, вызвавший другой сценарий, должен остаться атомарным,
    а вложенный ``begin()`` зафиксировал бы половину работы на внутреннем выходе.
    """
    if session.in_transaction():
        yield session
        return
    async with session.begin():
        yield session


class Database:
    """Владелец движка и фабрики сессий сервиса.

    Живет в ``app.state``, а не в переменной модуля: глобальный движок заставил бы тесты делить пул и зависеть от
    порядка запуска.
    """

    def __init__(self, engine: AsyncEngine, *, session_info: Mapping[str, object] | None = None) -> None:
        self._engine = engine
        self._session_factory = create_session_factory(engine, info=session_info)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    async def check(self) -> None:
        """Проверка для /ready: БД отвечает на ``SELECT 1``."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Закрыть соединения пула. Вызывается при остановке."""
        await self._engine.dispose()


def get_database(request: Request) -> Database:
    """БД запущенного приложения."""
    database = getattr(request.app.state, "database", None)
    if not isinstance(database, Database):
        raise RuntimeError("в app.state нет database: вызовите use_database в lifespan до обслуживания запросов")
    return database


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос без открытой транзакции – транзакцию открывает сценарий."""
    async with get_database(request).session_factory() as session:
        yield session
