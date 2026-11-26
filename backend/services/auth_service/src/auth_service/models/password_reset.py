"""Хеши одноразовых токенов и окна ограничения запросов."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from auth_service.models.base import Base


class PasswordResetRow(Base):
    __tablename__ = "password_reset_tokens"
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    __table_args__ = (Index("password_reset_tokens_expires_at_idx", "expires_at"),)


class ResetRateRow(Base):
    __tablename__ = "password_reset_limits"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    requested_at: Mapped[datetime]
