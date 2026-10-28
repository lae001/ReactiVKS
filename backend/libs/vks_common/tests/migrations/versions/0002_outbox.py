"""Таблица outbox – для интеграционных тестов vks_common.kafka (та же, что в схемах сервисов, database.md)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="outbox_pkey"),
        sa.UniqueConstraint("event_id", name="outbox_event_id_uk"),
        schema="auth",
    )
    op.create_index(
        "outbox_unpublished_idx", "outbox", ["id"], schema="auth", postgresql_where=sa.text("published_at IS NULL")
    )


def downgrade() -> None:
    op.drop_table("outbox", schema="auth")
