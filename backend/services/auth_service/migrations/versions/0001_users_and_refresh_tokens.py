"""Учетные записи и refresh-токены (схема auth, database.md).

Таблицы password_reset_tokens и outbox создаются миграциями задач восстановления пароля и событий user.events.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, CITEXT

revision = "0001"
down_revision = None

SCHEMA = "auth"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="organizer", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.UniqueConstraint("email", name=op.f("users_email_uk")),
        sa.CheckConstraint(
            r"email ~ '^[^@\s]+@[^@\s]+$' AND char_length(email) <= 254",
            name=op.f("users_email_ck"),
        ),
        sa.CheckConstraint("char_length(display_name) BETWEEN 1 AND 100", name=op.f("users_display_name_ck")),
        sa.CheckConstraint("role IN ('organizer', 'admin')", name=op.f("users_role_ck")),
        sa.CheckConstraint("status IN ('active', 'blocked')", name=op.f("users_status_ck")),
        schema=SCHEMA,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", BYTEA(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("refresh_tokens_pkey")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("refresh_tokens_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("refresh_tokens_token_hash_uk")),
        schema=SCHEMA,
    )
    op.create_index(op.f("refresh_tokens_user_id_idx"), "refresh_tokens", ["user_id"], schema=SCHEMA)
    op.create_index(op.f("refresh_tokens_family_id_idx"), "refresh_tokens", ["family_id"], schema=SCHEMA)
    op.create_index(op.f("refresh_tokens_expires_at_idx"), "refresh_tokens", ["expires_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("refresh_tokens", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
