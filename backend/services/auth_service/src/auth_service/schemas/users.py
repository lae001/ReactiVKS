"""Схема пользователя в ответах."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from auth_service.domain.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from auth_service.domain.users import MAX_DISPLAY_NAME_LENGTH, User

__all__ = ["ChangePasswordRequest", "RenameRequest", "UserResponse"]

# Текущий пароль мог быть задан при прежней политике: граница лишь не дает прислать мегабайт.
_MAX_CURRENT_PASSWORD_LENGTH = 1024


class RenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH, examples=["Иван Петров"])


class ChangePasswordRequest(BaseModel):
    """Ограничения длины – для OpenAPI и типов фронтенда; букву и цифру в новом пароле проверяет домен."""

    current_password: str = Field(max_length=_MAX_CURRENT_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    """``User`` контракта: без хеша пароля, статуса и служебных полей."""

    id: UUID
    email: str
    display_name: str
    role: Literal["organizer", "admin"]

    @classmethod
    def from_domain(cls, user: User) -> UserResponse:
        return cls(id=user.id, email=user.email, display_name=user.display_name, role=user.role.value)
