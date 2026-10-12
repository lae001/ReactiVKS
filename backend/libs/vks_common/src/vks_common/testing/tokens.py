"""Access-токены для тестов сервисов, которые их проверяют.

Ключ генерируется на месте и нигде не хранится. Токены подписываются так же, как их подписывает auth-service, и
проверяются настоящим :class:`~vks_common.auth.TokenVerifier`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from vks_common.auth import ALGORITHM, ROLE_ORGANIZER, StaticKeys, TokenVerifier

__all__ = ["TokenFactory"]


class TokenFactory:
    """Пара ключей и выпуск токенов с нужными claims."""

    def __init__(self, *, issuer: str = "vks-auth", audience: str = "vks", kid: str = "test-key") -> None:
        self.issuer = issuer
        self.audience = audience
        self.kid = kid
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def keys(self) -> StaticKeys:
        return StaticKeys({self.kid: self._private_key.public_key()})

    def verifier(self) -> TokenVerifier:
        return TokenVerifier(keys=self.keys, issuer=self.issuer, audience=self.audience)

    def issue(
        self,
        *,
        user_id: UUID | None = None,
        role: str = ROLE_ORGANIZER,
        name: str = "Иван Петров",
        issued_at: datetime | None = None,
        lifetime: timedelta = timedelta(minutes=15),
        claims: Mapping[str, object] | None = None,
    ) -> str:
        """Подписанный токен; ``claims`` заменяют или добавляют claims (значение ``None`` – удалить claim)."""
        moment = issued_at or datetime.now(UTC)
        payload: dict[str, object] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(user_id or uuid4()),
            "role": role,
            "name": name,
            "iat": int(moment.timestamp()),
            "exp": int((moment + lifetime).timestamp()),
            "jti": str(uuid4()),
        }
        payload.update(claims or {})
        payload = {key: value for key, value in payload.items() if value is not None}
        return jwt.encode(payload, self._private_key, algorithm=ALGORITHM, headers={"kid": self.kid})
