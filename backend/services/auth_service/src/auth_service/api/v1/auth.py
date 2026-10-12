"""Эндпоинты ``/api/v1/auth`` (docs/api/rest-api.md, раздел 2). Все анонимные: проверяемые данные – в запросе."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from auth_service.api.v1.dependencies import PublishedKeysScenario, RegisterOrganizerScenario, Settings
from auth_service.schemas.auth import AuthConfigResponse, JsonWebKey, JwksResponse, RegisterRequest
from auth_service.schemas.users import UserResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Ключи меняются при ротации раз в месяцы, а сервисы перечитывают JWKS при неизвестном kid: кеш на 5 минут безопасен.
_JWKS_CACHE_CONTROL = "public, max-age=300"


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация организатора",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Регистрация выключена"},
        status.HTTP_409_CONFLICT: {"description": "email_taken"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Формат адреса, имени или пароля"},
    },
)
async def register(body: RegisterRequest, scenario: RegisterOrganizerScenario) -> UserResponse:
    """Учетная запись сразу активна; токены не выдаются – после регистрации клиент вызывает `login`."""
    user = await scenario.execute(email=body.email, password=body.password, display_name=body.display_name)
    return UserResponse.from_domain(user)


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
