"""Порт ключа подписи access-токенов.

Проверять токены здесь не нужно: их проверяют сервисы, которые их получают (``vks_common.auth``).
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["PublicJwk", "TokenSigner"]

# Одна запись массива ``keys`` документа JWKS (RFC 7517).
PublicJwk = dict[str, str]


class TokenSigner(Protocol):
    """Текущий ключ подписи и публичные ключи, которые нужно опубликовать в JWKS."""

    @property
    def kid(self) -> str:
        """Имя текущего ключа – в заголовке JWT и в JWKS."""
        ...

    def sign(self, claims: dict[str, object]) -> str:
        """Компактный JWS этих claims с ``kid`` в заголовке."""
        ...

    def published_keys(self) -> list[PublicJwk]:
        """Публичные ключи для JWKS: текущий и, на время ротации, прежний."""
        ...
