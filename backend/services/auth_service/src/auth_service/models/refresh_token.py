"""Таблица ``auth.refresh_tokens``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, LargeBinary, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from auth_service.models.base import Base

__all__ = ["RefreshTokenRow"]


class RefreshTokenRow(Base):
    """Один выданный refresh-токен.

    Хранится только SHA-256 токена. ``family_id`` связывает токены одной цепочки ротаций (один вход): повторное
    предъявление уже обмененного токена отзывает всю семью. Строка обмененного токена не удаляется – иначе
    повторное предъявление нельзя было бы распознать; ``replaced_by`` указывает на преемника.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    family_id: Mapped[UUID]
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by: Mapped[UUID | None]
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("token_hash"),
        Index(None, "user_id"),
        Index(None, "family_id"),
        # Для фоновой очистки истекших токенов (background-jobs.md).
        Index(None, "expires_at"),
    )
