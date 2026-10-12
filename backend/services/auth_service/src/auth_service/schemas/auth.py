"""Схемы эндпоинтов ``/api/v1/auth``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from auth_service.domain.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from auth_service.domain.users import MAX_DISPLAY_NAME_LENGTH, MAX_EMAIL_LENGTH
from auth_service.schemas.users import UserResponse

__all__ = ["AuthConfigResponse", "JsonWebKey", "JwksResponse", "LoginRequest", "RegisterRequest", "TokenResponse"]

# Вход принимает пароль любой длины до этой границы: политика могла измениться после того, как пароль задали, а
# граница лишь не дает прислать мегабайт.
_MAX_LOGIN_PASSWORD_LENGTH = 1024


class RegisterRequest(BaseModel):
    """Ограничения длины – для OpenAPI и типов фронтенда; остальные правила (формат адреса, буква и цифра в пароле)
    проверяет домен и отвечает 422 с указанием поля."""

    email: str = Field(max_length=MAX_EMAIL_LENGTH, examples=["ivan@example.ru"])
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH, examples=["Иван Петров"])


class LoginRequest(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH, examples=["ivan@example.ru"])
    password: str = Field(max_length=_MAX_LOGIN_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    """Access-токен – в теле (клиент держит его в памяти), refresh-токен – только в httpOnly-cookie."""

    access_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - схема авторизации, а не пароль
    expires_in: int = Field(description="Срок access-токена, с", examples=[900])
    user: UserResponse


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
