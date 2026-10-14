"""Эндпоинты ``/api/v1/auth`` (docs/api/rest-api.md, раздел 2). Все анонимные: проверяемые данные – в запросе."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from auth_service.api.v1.cookies import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    cleared_refresh_cookie_header,
    set_refresh_cookie,
)
from auth_service.api.v1.dependencies import (
    CurrentClock,
    LoginScenario,
    LogoutScenario,
    PublishedKeysScenario,
    RefreshSessionScenario,
    RegisterOrganizerScenario,
    Settings,
)
from auth_service.domain.errors import SessionInvalid
from auth_service.schemas.auth import (
    AuthConfigResponse,
    JsonWebKey,
    JwksResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from auth_service.schemas.users import UserResponse
from auth_service.services.sessions import IssuedSession

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE, include_in_schema=False)]

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


@router.post(
    "/login",
    summary="Вход",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "invalid_credentials"},
        status.HTTP_403_FORBIDDEN: {"description": "user_blocked – только при верном пароле"},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    scenario: LoginScenario,
    settings: Settings,
    clock: CurrentClock,
) -> TokenResponse:
    """Access-токен – в теле, refresh-токен – в cookie `vks_refresh`.

    Неизвестный адрес и неверный пароль отвечают одинаково – и телом, и временем ответа.
    """
    issued = await scenario.execute(
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
    )
    return _session_response(issued, response, settings=settings, clock=clock)


@router.post(
    "/refresh",
    summary="Обновление токенов",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет cookie, токен неизвестен, истек или отозван"}},
)
async def refresh(
    request: Request,
    response: Response,
    scenario: RefreshSessionScenario,
    settings: Settings,
    clock: CurrentClock,
    refresh_token: RefreshCookie = None,
) -> TokenResponse:
    """Ротация: старый refresh-токен больше не действует, в cookie – новый.

    Повторное предъявление уже обмененного токена отзывает всю его семью (это устройство разлогинено). Причина
    `401` не раскрывается; негодная cookie стирается.
    """
    try:
        issued = await scenario.execute(refresh_token=refresh_token, user_agent=request.headers.get("user-agent"))
    except SessionInvalid as error:
        raise SessionInvalid(
            headers={"set-cookie": cleared_refresh_cookie_header(secure=settings.auth_refresh_cookie_secure)}
        ) from error
    return _session_response(issued, response, settings=settings, clock=clock)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
async def logout(
    response: Response, scenario: LogoutScenario, settings: Settings, refresh_token: RefreshCookie = None
) -> None:
    """Отзывает семью текущего refresh-токена и стирает cookie. `204` всегда – выход можно повторять.

    Выданный access-токен действует до истечения срока (до 15 минут): клиент просто забывает его.
    """
    await scenario.execute(refresh_token=refresh_token)
    clear_refresh_cookie(response, secure=settings.auth_refresh_cookie_secure)


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


def _session_response(
    issued: IssuedSession, response: Response, *, settings: Settings, clock: CurrentClock
) -> TokenResponse:
    """Одно место, где выпущенная пара становится телом и cookie: вход и обмен отвечают одинаково."""
    set_refresh_cookie(
        response,
        issued.refresh_token,
        expires_at=issued.refresh_expires_at,
        now=clock.now(),
        secure=settings.auth_refresh_cookie_secure,
    )
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.access_expires_in,
        user=UserResponse.from_domain(issued.user),
    )
