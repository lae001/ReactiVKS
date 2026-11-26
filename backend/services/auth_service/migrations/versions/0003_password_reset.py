"""Одноразовое восстановление пароля и ограничение частоты (EMO-101)."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table("password_reset_tokens",
        sa.Column("token_hash", sa.LargeBinary(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)), schema="auth")
    op.create_index("password_reset_tokens_expires_at_idx", "password_reset_tokens", ["expires_at"], schema="auth")
    op.create_table("password_reset_limits",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False), schema="auth")


def downgrade() -> None:
    op.drop_table("password_reset_limits", schema="auth")
    op.drop_table("password_reset_tokens", schema="auth")
