"""Схемы эндпоинтов ``/api/v1/auth``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from auth_service.domain.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from auth_service.domain.users import MAX_DISPLAY_NAME_LENGTH, MAX_EMAIL_LENGTH

__all__ = ["AuthConfigResponse", "JsonWebKey", "JwksResponse", "RegisterRequest"]


class RegisterRequest(BaseModel):
    """Ограничения длины – для OpenAPI и типов фронтенда; остальные правила (формат адреса, буква и цифра в пароле)
    проверяет домен и отвечает 422 с указанием поля."""

    email: str = Field(max_length=MAX_EMAIL_LENGTH, examples=["ivan@example.ru"])
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH, examples=["Иван Петров"])


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
