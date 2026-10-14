"""Типизированное представление claims проверенного access-токена.

Claims разбираются один раз в :class:`AuthenticatedUser`; дальше сервис словарь claims не читает. Состав claims –
docs/architecture/05-security-privacy.md, §5.2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

__all__ = ["ROLE_ADMIN", "ROLE_ORGANIZER", "USER_ROLES", "AuthenticatedUser", "user_from_claims"]

ROLE_ORGANIZER = "organizer"
ROLE_ADMIN = "admin"
USER_ROLES = frozenset({ROLE_ORGANIZER, ROLE_ADMIN})


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Кто вызывает – по токену с проверенной подписью."""

    user_id: UUID
    role: str
    name: str
    token_id: str
    expires_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def user_from_claims(claims: Mapping[str, object]) -> AuthenticatedUser:
    """Разобрать claims проверенного токена. ``ValueError`` – токен не описывает пользователя платформы."""
    subject = claims.get("sub")
    role = claims.get("role")
    name = claims.get("name")
    token_id = claims.get("jti")
    expires_at = claims.get("exp")
    if not isinstance(subject, str):
        raise ValueError("в токене нет sub")
    if role not in USER_ROLES or not isinstance(role, str):
        raise ValueError("в токене неизвестная роль")
    if not isinstance(name, str) or not isinstance(token_id, str):
        raise ValueError("в токене нет name или jti")
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise ValueError("в токене нет exp")
    return AuthenticatedUser(
        user_id=UUID(subject),
        role=role,
        name=name,
        token_id=token_id,
        expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
    )
