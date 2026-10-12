"""Схемы эндпоинтов ``/api/v1/auth``."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["AuthConfigResponse", "JsonWebKey", "JwksResponse"]


class AuthConfigResponse(BaseModel):
    """Публичные флаги: фронтенд прячет то, что выключено."""

    registration_enabled: bool
    password_reset_enabled: bool


class JsonWebKey(BaseModel):
    """Публичный ключ RSA (RFC 7517)."""

    kty: str = Field(examples=["RSA"])
    kid: str
    use: str = Field(examples=["sig"])
    alg: str = Field(examples=["RS256"])
    n: str
    e: str = Field(examples=["AQAB"])


class JwksResponse(BaseModel):
    keys: list[JsonWebKey]
