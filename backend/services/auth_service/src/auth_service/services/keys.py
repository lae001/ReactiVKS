"""Публичные ключи для JWKS."""

from __future__ import annotations

from auth_service.domain.signing import PublicJwk, TokenSigner

__all__ = ["PublishedKeys"]


class PublishedKeys:
    """Ключи, по которым остальные сервисы проверяют access-токены: текущий и, на время ротации, прежний."""

    def __init__(self, signer: TokenSigner) -> None:
        self._signer = signer

    def execute(self) -> list[PublicJwk]:
        return self._signer.published_keys()
