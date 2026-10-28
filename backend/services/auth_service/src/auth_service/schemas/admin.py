"""Схемы ``/api/v1/admin/users``."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from auth_service.domain.users import User
from auth_service.schemas.users import UserResponse

__all__ = ["AdminUserPageResponse", "AdminUserResponse", "UpdateUserRequest"]

RoleValue = Literal["organizer", "admin"]
StatusValue = Literal["active", "blocked"]


class AdminUserResponse(UserResponse):
    """``AdminUser`` контракта: ``User`` и то, что нужно администратору."""

    status: StatusValue
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_domain(cls, user: User) -> AdminUserResponse:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role.value,
            status=user.status.value,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class AdminUserPageResponse(BaseModel):
    items: list[AdminUserResponse]
    next_cursor: str | None = Field(description="Передать в `cursor`, чтобы получить следующую страницу")


class UpdateUserRequest(BaseModel):
    """Не переданное поле не меняется."""

    status: StatusValue | None = None
    role: RoleValue | None = None
