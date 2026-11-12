"""Отчеты и ключевые моменты (EMO-87)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "markers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("(kind = 'manual') = (created_by IS NOT NULL)", name=op.f("markers_author_ck")),
        sa.CheckConstraint("kind IN ('auto_shift','manual')", name=op.f("markers_kind_ck")),
        sa.CheckConstraint("char_length(label) BETWEEN 1 AND 200", name=op.f("markers_label_ck")),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["analytics.meeting_projection.meeting_id"],
            name=op.f("markers_meeting_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("markers_pkey")),
        schema="analytics",
    )
    op.create_index("markers_meeting_ts_idx", "markers", ["meeting_id", "ts"], unique=False, schema="analytics")
    op.create_table(
        "reports",
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("target_partition", sa.Integer(), nullable=True),
        sa.Column("target_offset", sa.BigInteger(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status <> 'ready' OR (summary IS NOT NULL AND generated_at IS NOT NULL)", name=op.f("reports_ready_ck")
        ),
        sa.CheckConstraint("status IN ('pending','ready','failed')", name=op.f("reports_status_ck")),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["analytics.meeting_projection.meeting_id"],
            name=op.f("reports_meeting_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("meeting_id", name=op.f("reports_pkey")),
        schema="analytics",
    )
    op.create_index(
        "reports_pending_idx",
        "reports",
        ["updated_at"],
        unique=False,
        schema="analytics",
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "reports_pending_idx", table_name="reports", schema="analytics", postgresql_where=sa.text("status = 'pending'")
    )
    op.drop_table("reports", schema="analytics")
    op.drop_index("markers_meeting_ts_idx", table_name="markers", schema="analytics")
    op.drop_table("markers", schema="analytics")
