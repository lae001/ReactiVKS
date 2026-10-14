"""Ключи RS256 сервиса за портом :class:`~auth_service.domain.signing.TokenSigner`.

Единственный модуль, который знает про PEM, RSA и PyJWT. Закрытый ключ приходит файлом и живет только в памяти.
``kid`` – отпечаток публичного ключа по RFC 7638: у одного и того же ключа всегда одно имя, и перезапуск сервиса не
делает выданные токены непроверяемыми.
"""

from __future__ import annotations

import base64
import hashlib
import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from auth_service.domain.signing import PublicJwk

__all__ = ["MIN_KEY_SIZE_BITS", "InvalidSigningKey", "RsaKeyRing", "jwk_thumbprint"]

ALGORITHM = "RS256"
MIN_KEY_SIZE_BITS = 2048


class InvalidSigningKey(ValueError):
    """Ключ из настроек не годится для подписи RS256. Ошибка конфигурации при старте."""


class RsaKeyRing:
    """Текущий закрытый ключ и, на время ротации, публичная часть прежнего."""

    def __init__(self, private_key_pem: str, *, previous_public_key_pem: str | None = None) -> None:
        self._private_key = _load_private_key(private_key_pem)
        current = self._private_key.public_key()
        self._kid = jwk_thumbprint(_public_jwk(current))
        self._public_keys: dict[str, RSAPublicKey] = {self._kid: current}
        if previous_public_key_pem is not None:
            previous = _load_public_key(previous_public_key_pem)
            self._public_keys.setdefault(jwk_thumbprint(_public_jwk(previous)), previous)

    @property
    def kid(self) -> str:
        return self._kid

    def sign(self, claims: dict[str, object]) -> str:
        return jwt.encode(claims, self._private_key, algorithm=ALGORITHM, headers={"kid": self._kid})

    def published_keys(self) -> list[PublicJwk]:
        return [
            {**_public_jwk(key), "kid": kid, "use": "sig", "alg": ALGORITHM} for kid, key in self._public_keys.items()
        ]

    def verification_keys(self) -> dict[str, RSAPublicKey]:
        """Публичные ключи по ``kid`` – auth-service проверяет свои токены ими же, без запроса к своему JWKS."""
        return dict(self._public_keys)


def jwk_thumbprint(jwk: PublicJwk) -> str:
    """Отпечаток RFC 7638: SHA-256 канонического JWK (только ``e``, ``kty``, ``n``), base64url без выравнивания."""
    canonical = json.dumps({"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _public_jwk(key: RSAPublicKey) -> PublicJwk:
    numbers = key.public_numbers()
    return {"kty": "RSA", "n": _b64url_uint(numbers.n), "e": _b64url_uint(numbers.e)}


def _b64url_uint(value: int) -> str:
    """Base64url беззнакового целого минимальной длины (RFC 7518: без ведущих нулевых октетов)."""
    width = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


def _load_private_key(pem: str) -> RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as error:
        # Сообщение библиотеки различает «не PEM» и «зашифрован» и не цитирует ключ.
        raise InvalidSigningKey(f"закрытый ключ не читается: {error}") from error
    if not isinstance(key, RSAPrivateKey):
        raise InvalidSigningKey(f"нужен закрытый ключ RSA, получен {type(key).__name__}")
    if key.key_size < MIN_KEY_SIZE_BITS:
        raise InvalidSigningKey(f"ключ должен быть не короче {MIN_KEY_SIZE_BITS} бит, получено {key.key_size}")
    return key


def _load_public_key(pem: str) -> RSAPublicKey:
    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise InvalidSigningKey(f"публичный ключ не читается: {error}") from error
    if not isinstance(key, RSAPublicKey):
        raise InvalidSigningKey(f"нужен публичный ключ RSA, получен {type(key).__name__}")
    return key
