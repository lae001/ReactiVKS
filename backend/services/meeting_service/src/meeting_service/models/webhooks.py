"""Таблицы ``meeting.processed_webhooks`` и ``meeting.blocked_users``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base

__all__ = ["BlockedUserRow", "ProcessedWebhookRow"]


class ProcessedWebhookRow(Base):
    """Обработанный вебхук LiveKit: отметка пишется в той же транзакции, что и его эффект."""

    __tablename__ = "processed_webhooks"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (Index(None, "received_at"),)


class BlockedUserRow(Base):
    """Проекция ``user.events``: заблокированный организатор. Разблокировка удаляет строку.

    ``user_id`` – без внешнего ключа: учетные записи живут в схеме auth-service.
    """

    __tablename__ = "blocked_users"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    blocked_at: Mapped[datetime] = mapped_column(server_default=func.now())
