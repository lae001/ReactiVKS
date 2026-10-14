"""Различение ошибок целостности по SQLSTATE и имени ограничения.

Драйвер asyncpg через SQLAlchemy кладет имя ограничения только в ``__cause__``; функции здесь прячут эту деталь от
сервисов.
"""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError

__all__ = [
    "SQLSTATE_CHECK_VIOLATION",
    "SQLSTATE_FOREIGN_KEY_VIOLATION",
    "SQLSTATE_UNIQUE_VIOLATION",
    "constraint_name_of",
    "is_unique_violation",
    "sqlstate_of",
]

SQLSTATE_UNIQUE_VIOLATION = "23505"
SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"
SQLSTATE_CHECK_VIOLATION = "23514"


def sqlstate_of(error: DBAPIError) -> str | None:
    """Пятисимвольный код ответа PostgreSQL, если он есть."""
    code = getattr(error.orig, "sqlstate", None)
    return code if isinstance(code, str) else None


def constraint_name_of(error: DBAPIError) -> str | None:
    """Имя нарушенного ограничения или индекса, если драйвер его сообщил.

    Именно имя превращает «что-то не уникально» в «e-mail занят»: таблицу с двумя уникальными ограничениями по
    одному SQLSTATE не различить.
    """
    dialect_error = error.orig
    if dialect_error is None:
        return None
    name = getattr(dialect_error, "constraint_name", None)
    if isinstance(name, str):
        return name
    name = getattr(dialect_error.__cause__, "constraint_name", None)
    return name if isinstance(name, str) else None


def is_unique_violation(error: DBAPIError, *, constraint: str | None = None) -> bool:
    """Это ``23505``, при необходимости – именно от этого ограничения."""
    if sqlstate_of(error) != SQLSTATE_UNIQUE_VIOLATION:
        return False
    return constraint is None or constraint_name_of(error) == constraint
