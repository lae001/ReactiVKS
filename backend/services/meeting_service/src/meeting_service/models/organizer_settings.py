"""Таблица ``meeting.organizer_settings``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, SmallInteger, func, true
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base

__all__ = ["OrganizerSettingsRow"]


class OrganizerSettingsRow(Base):
    """Настройки анализа по умолчанию для новых встреч организатора. Строки нет – действуют значения по умолчанию.

    ``user_id`` – ``sub`` из JWT, без внешнего ключа: учетные записи живут в другой схеме.
    """

    __tablename__ = "organizer_settings"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    analysis_enabled_default: Mapped[bool] = mapped_column(server_default=true())
    analysis_fps_default: Mapped[int] = mapped_column(SmallInteger, server_default="3")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (CheckConstraint("analysis_fps_default BETWEEN 2 AND 5", name="analysis_fps_default"),)
