"""Очередь синхронизации согласия с LiveKit (EMO-84)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"

SCHEMA = "meeting"


def upgrade() -> None:
    op.create_table(
        "livekit_sync_queue",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True)),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("livekit_sync_queue_next_attempt_at_idx", "livekit_sync_queue", ["next_attempt_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("livekit_sync_queue", schema=SCHEMA)
