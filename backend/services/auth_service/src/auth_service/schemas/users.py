"""Схема пользователя в ответах."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from auth_service.domain.users import MAX_DISPLAY_NAME_LENGTH, User

__all__ = ["RenameRequest", "UserResponse"]


class RenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH, examples=["Иван Петров"])


class UserResponse(BaseModel):
    """``User`` контракта: без хеша пароля, статуса и служебных полей."""

    id: UUID
    email: str
    display_name: str
    role: Literal["organizer", "admin"]

    @classmethod
    def from_domain(cls, user: User) -> UserResponse:
        return cls(id=user.id, email=user.email, display_name=user.display_name, role=user.role.value)
