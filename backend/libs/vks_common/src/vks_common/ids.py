"""Идентификаторы и случайные токены.

Идентификаторы сущностей – UUIDv7 (database.md): они монотонно растут во времени, поэтому вставка в индекс по
первичному ключу идет в конец, а курсорная пагинация по ``(created_at, id)`` устойчива.
"""

from __future__ import annotations

import secrets
from uuid import UUID

import uuid6

__all__ = ["DEFAULT_TOKEN_BYTES", "new_id", "new_token"]

# 256 бит: у токена нет структуры, и перебор – единственная атака на него.
DEFAULT_TOKEN_BYTES = 32


def new_id() -> UUID:
    """Новый UUIDv7."""
    # uuid6 возвращает свой подкласс UUID; приводим к стандартному, чтобы сравнение и сериализация не зависели
    # от библиотеки.
    return UUID(int=uuid6.uuid7().int)


def new_token(nbytes: int = DEFAULT_TOKEN_BYTES) -> str:
    """Случайный токен в base64url без выравнивания."""
    return secrets.token_urlsafe(nbytes)
