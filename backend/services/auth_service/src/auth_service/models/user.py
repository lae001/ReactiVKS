"""Таблица ``auth.users``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from auth_service.models.base import Base

__all__ = ["UserRow"]


class UserRow(Base):
    """Учетная запись организатора или администратора.

    ``email`` – ``citext``: уникальность без учета регистра держит ограничение БД, а не проверка в коде.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default="organizer")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("email"),
        CheckConstraint(r"email ~ '^[^@\s]+@[^@\s]+$' AND char_length(email) <= 254", name="email"),
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 100", name="display_name"),
        CheckConstraint("role IN ('organizer', 'admin')", name="role"),
        CheckConstraint("status IN ('active', 'blocked')", name="status"),
    )
