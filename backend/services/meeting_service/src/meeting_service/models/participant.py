"""Таблица ``meeting.participants``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, LargeBinary, Text, UniqueConstraint, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base

__all__ = ["ParticipantRow"]


class ParticipantRow(Base):
    """Участник встречи. ``id`` дает identity в LiveKit: ``p_<id>``.

    У организатора есть ``user_id`` и нет ``participant_token_hash``, у гостя – наоборот (``participants_identity_ck``).
    Токен гостя хранится только хешем.
    """

    __tablename__ = "participants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meeting.meetings.id", ondelete="CASCADE"))
    user_id: Mapped[UUID | None]
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    consent_state: Mapped[str] = mapped_column(Text)
    participant_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Удален организатором: повторный вход по токену этого участника запрещен.
    is_removed: Mapped[bool] = mapped_column(server_default=false())
    # Присутствие в комнате – по вебхукам LiveKit: в комнате, если последний вход позже последнего выхода.
    first_joined_at: Mapped[datetime | None]
    last_joined_at: Mapped[datetime | None]
    last_left_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("participant_token_hash"),
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 64", name="display_name"),
        CheckConstraint("role IN ('organizer', 'guest')", name="role"),
        CheckConstraint("consent_state IN ('granted', 'denied', 'revoked', 'not_required')", name="consent_state"),
        CheckConstraint(
            "(role = 'organizer' AND user_id IS NOT NULL AND participant_token_hash IS NULL) OR "
            "(role = 'guest' AND user_id IS NULL AND participant_token_hash IS NOT NULL)",
            name="identity",
        ),
        Index(None, "meeting_id"),
        # Организатор – один участник своей встречи, сколько бы раз ни входил.
        Index(
            "participants_meeting_id_user_id_uk",
            "meeting_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )
