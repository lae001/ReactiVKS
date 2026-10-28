"""Таблица ``meeting.consents``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base

__all__ = ["ConsentRow"]


class ConsentRow(Base):
    """Журнал решений о согласии на анализ эмоций – только добавление.

    Намеренно без внешних ключей и со снимками имени участника и названия встречи: журнал хранится 3 года и должен
    пережить очистку встреч (подтверждение согласия по 152-ФЗ).
    """

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    meeting_id: Mapped[UUID]
    participant_id: Mapped[UUID]
    display_name: Mapped[str] = mapped_column(Text)
    meeting_title: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    notice_version: Mapped[str] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("decision IN ('granted', 'denied', 'revoked')", name="decision"),
        Index(None, "participant_id", "decided_at"),
        Index(None, "meeting_id"),
        Index(None, "decided_at"),
    )
