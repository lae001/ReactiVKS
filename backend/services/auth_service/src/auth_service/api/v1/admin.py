"""Эндпоинты ``/api/v1/admin/users`` – управление учетными записями (только роль ``admin``)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.exceptions import RequestValidationError

from auth_service.api.v1.dependencies import DeleteUserScenario, ListUsersScenario, UpdateUserScenario
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import InvalidCursor, Role, UserCursor, UserQuery, UserStatus
from auth_service.schemas.admin import AdminUserPageResponse, AdminUserResponse, StatusValue, UpdateUserRequest
from vks_common.auth import CurrentAdmin

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["admin"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Нет access-токена или он недействителен"},
        status.HTTP_403_FORBIDDEN: {"description": "Роль не admin"},
    },
)

_NOT_FOUND: dict[int | str, dict[str, object]] = {status.HTTP_404_NOT_FOUND: {"description": "Пользователя нет"}}
_LAST_ADMIN: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"description": "last_admin – себя или последнего администратора"}
}


@router.get("", summary="Список пользователей")
async def list_users(
    admin: CurrentAdmin,
    scenario: ListUsersScenario,
    q: Annotated[str | None, Query(max_length=100, description="Подстрока e-mail или имени")] = None,
    status_filter: Annotated[StatusValue | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> AdminUserPageResponse:
    """Новые сверху."""
    page = await scenario.execute(
        query=UserQuery(
            text=(q.strip() or None) if q else None,
            status=UserStatus(status_filter) if status_filter else None,
        ),
        limit=limit,
        after=_decode_cursor(cursor) if cursor else None,
    )
    return AdminUserPageResponse(
        items=[AdminUserResponse.from_domain(user) for user in page.items],
        next_cursor=page.next_cursor.encode() if page.next_cursor is not None else None,
    )


@router.patch("/{user_id}", summary="Блокировка, разблокировка, роль", responses=_NOT_FOUND | _LAST_ADMIN)
async def update_user(
    user_id: UUID, body: UpdateUserRequest, admin: CurrentAdmin, scenario: UpdateUserScenario
) -> AdminUserResponse:
    """Блокировка завершает все сессии пользователя и закрывает ему вход во встречи."""
    user = await scenario.execute(
        actor_id=UserId(admin.user_id),
        user_id=UserId(user_id),
        status=UserStatus(body.status) if body.status else None,
        role=Role(body.role) if body.role else None,
    )
    return AdminUserResponse.from_domain(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя",
    responses=_NOT_FOUND | _LAST_ADMIN,
)
async def delete_user(user_id: UUID, admin: CurrentAdmin, scenario: DeleteUserScenario) -> None:
    """Встречи и аналитика пользователя удаляются другими сервисами по событию `user.deleted`."""
    await scenario.execute(actor_id=UserId(admin.user_id), user_id=UserId(user_id))


def _decode_cursor(value: str) -> UserCursor:
    try:
        return UserCursor.decode(value)
    except InvalidCursor as error:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "Cursor is not valid", "type": "value_error"}]
        ) from error
