"""Асинхронный движок SQLAlchemy.

Один движок на процесс: создается при старте, закрывается при остановке. Пул ограничен сознательно – безразмерный
пул прячет утечку соединений, пока PostgreSQL не начнет отказывать всем.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from vks_common.config import DatabaseServiceSettings

__all__ = ["create_engine", "create_engine_from_settings"]


def create_engine(
    url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_timeout_seconds: float = 5.0,
    application_name: str | None = None,
) -> AsyncEngine:
    """Движок для БД сервиса.

    ``pool_pre_ping`` стоит одного обращения при выдаче соединения и спасает первый запрос после перезапуска
    PostgreSQL. ``application_name`` показывает в ``pg_stat_activity``, чье это соединение.
    """
    connect_args: dict[str, object] = {}
    if application_name is not None:
        connect_args["server_settings"] = {"application_name": application_name}
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def create_engine_from_settings(settings: DatabaseServiceSettings) -> AsyncEngine:
    """Движок по настройкам сервиса."""
    return create_engine(
        settings.database_url_value,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
        application_name=settings.service_name,
    )
