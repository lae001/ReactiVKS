"""Таблица notes с именованным уникальным ограничением – для тестов транзакций и SQLSTATE."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.UniqueConstraint("title", name="notes_title_uk"),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_table("notes", schema="auth")
