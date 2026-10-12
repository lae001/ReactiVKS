"""Зависимости FastAPI, закрывающие эндпоинт проверкой токена (conventions.md, §12).

::

    @router.get("/users/me")
    async def read_me(user: CurrentUser, scenario: GetProfileScenario) -> UserResponse: ...

Токен читается через ``HTTPBearer`` FastAPI – поэтому каждый закрытый эндпоинт объявляет схему Bearer в OpenAPI,
и Swagger UI предлагает передать токен. Проверка владения ресурсом – в сценарии, а не здесь.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from vks_common.auth.claims import AuthenticatedUser
from vks_common.auth.verifier import InvalidToken, TokenVerifier
from vks_common.errors import Forbidden, Unauthorized
from vks_common.logging import bind_context, get_logger

__all__ = [
    "CurrentAdmin",
    "CurrentUser",
    "get_token_verifier",
    "require_admin",
    "require_user",
    "use_authentication",
]

_logger = get_logger(__name__)

# auto_error=False: отсутствие заголовка отклоняется здесь ответом problem+json, а не телом FastAPI по умолчанию.
_bearer = HTTPBearer(
    scheme_name="BearerToken",
    description="Access-токен из `POST /api/v1/auth/login`",
    auto_error=False,
)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def use_authentication(app: FastAPI, verifier: TokenVerifier) -> None:
    """Подключить проверяющего к приложению – там его найдут зависимости."""
    app.state.token_verifier = verifier


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    if not isinstance(verifier, TokenVerifier):
        raise RuntimeError("в app.state нет token_verifier: вызовите use_authentication при сборке приложения")
    return verifier


async def require_user(request: Request, credentials: BearerCredentials) -> AuthenticatedUser:
    """Организатор или администратор с действующим access-токеном."""
    token = credentials.credentials.strip() if credentials is not None else ""
    if not token:
        raise Unauthorized()
    try:
        user = await get_token_verifier(request).verify(token)
    except InvalidToken as error:
        raise Unauthorized() from error
    bind_context(user_id=str(user.user_id))
    return user


async def require_admin(user: Annotated[AuthenticatedUser, Depends(require_user)]) -> AuthenticatedUser:
    """То же, что :func:`require_user`, и роль ``admin``."""
    if not user.is_admin:
        _logger.info("access refused", required_role="admin")
        raise Forbidden("This operation requires the admin role")
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(require_user)]
CurrentAdmin = Annotated[AuthenticatedUser, Depends(require_admin)]
