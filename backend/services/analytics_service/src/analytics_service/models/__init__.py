"""Схема проекций, согласий и посекундных агрегатов."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import REAL

from vks_common.db import create_metadata
from vks_common.kafka import outbox_table

metadata = create_metadata("analytics")
OUTBOX = outbox_table(metadata)
meetings = Table(
    "meeting_projection",
    metadata,
    Column("meeting_id", Uuid, primary_key=True),
    Column("owner_id", Uuid, nullable=False),
    Column("title", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("analysis_enabled", Boolean, nullable=False, server_default=false()),
    Column("started_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('scheduled','active','ended','cancelled')", name="status"),
)
Index("meeting_projection_owner_idx", meetings.c.owner_id)
Index("meeting_projection_ended_idx", meetings.c.ended_at)

participants = Table(
    "participant_projection",
    metadata,
    Column("participant_id", Uuid, primary_key=True),
    Column("meeting_id", Uuid, ForeignKey(meetings.c.meeting_id, ondelete="CASCADE"), nullable=False),
    Column("display_name", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("consent_state", Text, nullable=False),
    Column("consent_decided_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("participant_projection_meeting_idx", participants.c.meeting_id)

consent_history = Table(
    "consent_history",
    metadata,
    Column("participant_id", Uuid, ForeignKey(participants.c.participant_id, ondelete="CASCADE"), primary_key=True),
    Column("decided_at", DateTime(timezone=True), primary_key=True),
    Column("is_granted", Boolean, nullable=False),
)

# Порядок столбцов соответствует общему контракту vks_contracts.ml_events.EMOTIONS.
PROBABILITIES = ("p_angry", "p_disgust", "p_fear", "p_happy", "p_sad", "p_surprise", "p_neutral")
series = Table(
    "emotion_series",
    metadata,
    Column("meeting_id", Uuid, primary_key=True),
    Column("participant_id", Uuid, primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("samples", SmallInteger, nullable=False),
    Column("face_samples", SmallInteger, nullable=False),
    *(Column(label, REAL) for label in PROBABILITIES),
    Column("model_version", Text, nullable=False),
    CheckConstraint("samples > 0 AND face_samples BETWEEN 0 AND samples", name="samples"),
    CheckConstraint(
        "(face_samples = 0 AND "
        + " AND ".join(f"{label} IS NULL" for label in PROBABILITIES)
        + ") OR (face_samples > 0 AND "
        + " AND ".join(f"({label} IS NOT NULL AND {label} BETWEEN 0 AND 1)" for label in PROBABILITIES)
        + ")",
        name="probs",
    ),
)
Index("emotion_series_meeting_ts_idx", series.c.meeting_id, series.c.ts)

sample_offsets = Table(
    "sample_offsets",
    metadata,
    Column("partition", Integer, primary_key=True, autoincrement=False),
    Column("next_offset", BigInteger, nullable=False),
)
deleted_meetings = Table("deleted_meetings", metadata, Column("meeting_id", Uuid, primary_key=True))
deleted_owners = Table("deleted_owners", metadata, Column("owner_id", Uuid, primary_key=True))
