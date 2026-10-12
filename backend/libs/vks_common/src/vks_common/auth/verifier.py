"""Проверка access-токена: подпись, затем обязательные claims.

- Только RS256; алгоритм никогда не берется из заголовка токена (атаки ``alg: none`` и подмена на HS256).
- ``iss`` и ``aud`` должны совпасть с настройками сервиса.
- Срок проверяется с небольшим допуском на расхождение часов.
"""

from __future__ import annotations

import jwt

from vks_common.auth.claims import AuthenticatedUser, user_from_claims
from vks_common.auth.keys import UnknownSigningKey, VerificationKeys
from vks_common.logging import get_logger

__all__ = ["ALGORITHM", "InvalidToken", "TokenVerifier"]

ALGORITHM = "RS256"

_logger = get_logger(__name__)


class InvalidToken(Exception):
    """Токен выпущен не платформой или больше не действует. Одна ошибка на все причины: клиенту причина не нужна."""


class TokenVerifier:
    """Проверяет токены ключами из переданного источника."""

    def __init__(self, *, keys: VerificationKeys, issuer: str, audience: str, leeway_seconds: int = 5) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway_seconds

    async def verify(self, token: str) -> AuthenticatedUser:
        """Проверить компактный JWS и вернуть пользователя из него."""
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str):
                raise InvalidToken("в заголовке токена нет kid")
            key = await self._keys.key_for(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
            )
        except UnknownSigningKey as error:
            raise InvalidToken("токен подписан неизвестным ключом") from error
        except jwt.InvalidTokenError as error:
            # Причина – в журнал: она нужна оператору, а не тому, кто прислал токен.
            _logger.info("token rejected", reason=type(error).__name__)
            raise InvalidToken("токен недействителен") from error

        try:
            return user_from_claims(claims)
        except ValueError as error:
            raise InvalidToken("токен не описывает пользователя") from error
