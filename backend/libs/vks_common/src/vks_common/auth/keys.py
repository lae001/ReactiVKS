"""Откуда сервис берет публичные ключи для проверки токенов.

Две реализации отвечают на один вопрос – «дай ключ с этим ``kid``»:

- :class:`StaticKeys` держит ключи, которые ему дали. Его использует auth-service: он владеет ключами и проверяет
  свои токены без HTTP-запроса к самому себе;
- :class:`~vks_common.auth.jwks.JwksKeys` загружает JWKS из auth-service и кеширует. Его используют остальные.

Проверяющий зависит от протокола, а не от реализации: правила (алгоритм, iss, aud, срок) написаны один раз.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt import PyJWK

__all__ = ["StaticKeys", "UnknownSigningKey", "VerificationKeys", "key_from_jwk", "key_from_pem"]


class UnknownSigningKey(LookupError):
    """Ключа с таким ``kid`` нет. Клиенту отвечают тем же ``401``, что и на неверную подпись."""


class VerificationKeys(Protocol):
    """Публичные ключи платформы по имени из заголовка токена."""

    async def key_for(self, kid: str) -> RSAPublicKey:
        """Ключ по ``kid``; если источник умеет – загрузить. Нет ключа – :class:`UnknownSigningKey`."""
        ...


class StaticKeys:
    """Фиксированный набор ключей – для сервиса, который ими владеет."""

    def __init__(self, keys: Mapping[str, RSAPublicKey]) -> None:
        self._keys = dict(keys)

    async def key_for(self, kid: str) -> RSAPublicKey:
        try:
            return self._keys[kid]
        except KeyError as error:
            raise UnknownSigningKey(kid) from error


def key_from_pem(public_pem: str) -> RSAPublicKey:
    """Публичный ключ из PEM. Не RSA – ошибка: платформа подписывает только RS256."""
    key = load_pem_public_key(public_pem.encode("ascii"))
    if not isinstance(key, RSAPublicKey):
        raise ValueError("ключ проверки – не публичный ключ RSA")
    return key


def key_from_jwk(jwk: Mapping[str, object]) -> RSAPublicKey:
    """Публичный ключ из записи JWKS. Чужой тип ключа – ошибка, а не молчаливый пропуск."""
    if jwk.get("kty") != "RSA":
        raise ValueError(f"неподдерживаемый тип ключа {jwk.get('kty')!r}")
    if jwk.get("use") not in (None, "sig"):
        raise ValueError(f"ключ не для подписи: use={jwk.get('use')!r}")
    key = PyJWK.from_dict(dict(jwk)).key
    if not isinstance(key, RSAPublicKey):
        raise ValueError("опубликованный ключ – не публичный ключ RSA")
    return key
