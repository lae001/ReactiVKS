"""Эндпоинты ``/api/v1/auth`` (docs/api/rest-api.md, раздел 2). Все анонимные: проверяемые данные – в запросе."""

from __future__ import annotations

from fastapi import APIRouter, Response

from auth_service.api.v1.dependencies import PublishedKeysScenario, Settings
from auth_service.schemas.auth import AuthConfigResponse, JsonWebKey, JwksResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Ключи меняются при ротации раз в месяцы, а сервисы перечитывают JWKS при неизвестном kid: кеш на 5 минут безопасен.
_JWKS_CACHE_CONTROL = "public, max-age=300"


@router.get("/config", summary="Публичные флаги")
async def read_config(settings: Settings) -> AuthConfigResponse:
    """Что включено: фронтенд по флагам прячет регистрацию и ссылку «Забыли пароль?»."""
    return AuthConfigResponse(
        registration_enabled=settings.auth_registration_enabled,
        # Восстановление пароля – дополнительная функция, требует SMTP; пока не реализовано.
        password_reset_enabled=False,
    )


@router.get("/.well-known/jwks.json", summary="Публичные ключи JWT")
async def read_jwks(scenario: PublishedKeysScenario, response: Response) -> JwksResponse:
    """Ключи, по которым сервисы проверяют access-токены RS256."""
    response.headers["Cache-Control"] = _JWKS_CACHE_CONTROL
    return JwksResponse(keys=[JsonWebKey.model_validate(jwk) for jwk in scenario.execute()])
