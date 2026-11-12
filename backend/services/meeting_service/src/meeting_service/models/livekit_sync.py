"""Очередь доставки атрибутов LiveKit."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Identity, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from meeting_service.models.base import Base


class LiveKitSyncRow(Base):
    __tablename__ = "livekit_sync_queue"
    __table_args__ = (Index("livekit_sync_queue_next_attempt_at_idx", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    meeting_id: Mapped[UUID]
    participant_id: Mapped[UUID] = mapped_column(unique=True)
    attributes: Mapped[dict[str, str]] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    locked_until: Mapped[datetime | None]
    next_attempt_at: Mapped[datetime]
