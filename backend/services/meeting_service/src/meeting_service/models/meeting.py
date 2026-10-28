"""Таблица ``meeting.meetings``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, SmallInteger, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base

__all__ = ["MeetingRow"]


class MeetingRow(Base):
    """Встреча. ``id`` – одновременно имя комнаты LiveKit.

    ``owner_name`` – снимок имени организатора на момент создания: его показывает лобби гостя, а в учетные записи
    чужой схемы meeting-service не ходит. Удаление мягкое (``deleted_at``), физическая очистка – через 30 дней.
    """

    __tablename__ = "meetings"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    owner_name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    invite_code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="scheduled")
    analysis_enabled: Mapped[bool]
    analysis_fps: Mapped[int] = mapped_column(SmallInteger)
    scheduled_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    end_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("invite_code"),
        CheckConstraint("invite_code ~ '^[a-z2-7]{10}$'", name="invite_code"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title"),
        CheckConstraint("char_length(owner_name) BETWEEN 1 AND 100", name="owner_name"),
        CheckConstraint("status IN ('scheduled', 'active', 'ended', 'cancelled')", name="status"),
        CheckConstraint("analysis_fps BETWEEN 2 AND 5", name="analysis_fps"),
        # Состояние и его отметки времени не расходятся: начатая встреча знает, когда началась, завершенная – когда
        # закончилась.
        CheckConstraint("status NOT IN ('active', 'ended') OR started_at IS NOT NULL", name="started_at"),
        CheckConstraint("status <> 'ended' OR ended_at IS NOT NULL", name="ended_at"),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('organizer', 'empty_timeout', 'admin')",
            name="end_reason",
        ),
        # История организатора – новые сверху, удаленные не показываются.
        Index(
            "meetings_owner_id_created_at_idx",
            "owner_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Фоновые задачи ищут незавершенные встречи.
        Index("meetings_status_idx", "status", postgresql_where=text("status IN ('scheduled', 'active')")),
        # Поиск по подстроке названия (GET /meetings?q=).
        Index(
            "meetings_title_idx",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        # Очистка мягко удаленных встреч через 30 дней.
        Index("meetings_deleted_at_idx", "deleted_at", postgresql_where=text("deleted_at IS NOT NULL")),
    )
