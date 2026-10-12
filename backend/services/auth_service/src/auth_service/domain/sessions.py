"""Правила пары токенов: claims access-токена и жизнь refresh-токена.

Access-токен – подписанное утверждение, которое каждый сервис проверяет сам; отозвать его нельзя, поэтому он живет
недолго. Refresh-токен – непрозрачный секрет: в БД лежит только его хеш, при каждом использовании он заменяется
новым (ротация), а повторное предъявление уже обмененного токена – признак кражи.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from auth_service.domain.identifiers import RefreshTokenId, SessionFamilyId, UserId
from auth_service.domain.users import User

__all__ = [
    "ACCESS_TOKEN_TTL",
    "REFRESH_TOKEN_TTL",
    "RefreshToken",
    "build_access_claims",
    "hash_refresh_token",
]

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """Сохраненный refresh-токен – только хеш, сам токен существует лишь в ответе, который его выдал."""

    id: RefreshTokenId
    user_id: UserId
    family_id: SessionFamilyId
    token_hash: bytes
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: RefreshTokenId | None = None

    @property
    def is_spent(self) -> bool:
        """Токен уже обменян или отозван. Предъявить его снова – значит, у кого-то осталась копия."""
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at <= now

    def rotated(self, *, successor: RefreshTokenId, now: datetime) -> RefreshToken:
        """Этот же токен, обменянный на преемника."""
        return replace(self, revoked_at=now, replaced_by=successor)


def build_access_claims(
    *,
    user: User,
    issuer: str,
    audience: str,
    token_id: UUID,
    issued_at: datetime,
    ttl: timedelta = ACCESS_TOKEN_TTL,
) -> dict[str, object]:
    """Claims access-токена (05-security-privacy.md, §5.2). ``iat`` и ``exp`` – целые секунды эпохи (RFC 7519)."""
    return {
        "iss": issuer,
        "aud": audience,
        "sub": str(user.id),
        "role": user.role.value,
        "name": user.display_name,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
        # Отличает два одинаковых в остальном токена в журнале или при разборе инцидента.
        "jti": str(token_id),
    }


def hash_refresh_token(token: str) -> bytes:
    """Значение ``refresh_tokens.token_hash``. SHA-256 достаточно: токен – 256 случайных бит, перебора нет."""
    return hashlib.sha256(token.encode("ascii")).digest()
