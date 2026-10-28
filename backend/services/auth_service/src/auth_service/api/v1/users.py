"""Эндпоинты ``/api/v1/users`` – профиль организатора или администратора (Bearer)."""

from __future__ import annotations

from fastapi import APIRouter, status

from auth_service.api.v1.dependencies import ChangePasswordScenario, GetProfileScenario, RenameUserScenario
from auth_service.domain.identifiers import UserId
from auth_service.schemas.users import ChangePasswordRequest, RenameRequest, UserResponse
from vks_common.auth import CurrentUser

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет access-токена или он недействителен"}},
)


@router.get("/me", summary="Профиль")
async def read_me(caller: CurrentUser, scenario: GetProfileScenario) -> UserResponse:
    user = await scenario.execute(user_id=UserId(caller.user_id))
    return UserResponse.from_domain(user)


@router.patch(
    "/me",
    summary="Смена отображаемого имени",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Имя пустое или длиннее 100 символов"}},
)
async def rename_me(body: RenameRequest, caller: CurrentUser, scenario: RenameUserScenario) -> UserResponse:
    """Claim `name` в access-токене обновится при следующем `POST /auth/refresh`."""
    user = await scenario.execute(user_id=UserId(caller.user_id), display_name=body.display_name)
    return UserResponse.from_domain(user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Смена пароля",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Нет access-токена или `invalid_credentials` – неверный текущий пароль"
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Новый пароль не удовлетворяет политике"},
    },
)
async def change_my_password(
    body: ChangePasswordRequest, caller: CurrentUser, scenario: ChangePasswordScenario
) -> None:
    """Завершает все сессии пользователя (refresh-токены отзываются); клиент входит заново с новым паролем."""
    await scenario.execute(
        user_id=UserId(caller.user_id),
        current_password=body.current_password,
        new_password=body.new_password,
    )
