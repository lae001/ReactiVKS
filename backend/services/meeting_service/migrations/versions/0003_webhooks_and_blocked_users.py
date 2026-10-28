"""Вебхуки LiveKit и проекция блокировок организаторов (EMO-69; database.md, схема meeting).

- ``processed_webhooks`` – идентификаторы обработанных вебхуков: повторная доставка ничего не меняет;
- ``blocked_users`` – заблокированные организаторы из ``user.events``: им закрыт вход во встречи;
- ``participants.last_joined_at`` – с ``last_left_at`` дает «участник сейчас в комнате».
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"

SCHEMA = "meeting"


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("last_joined_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "processed_webhooks",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("processed_webhooks_pkey")),
        schema=SCHEMA,
    )
    # Очистка старых отметок (дубликат вебхука приходит в пределах минут, а не дней).
    op.create_index("processed_webhooks_received_at_idx", "processed_webhooks", ["received_at"], schema=SCHEMA)

    op.create_table(
        "blocked_users",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("blocked_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("blocked_users_pkey")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("blocked_users", schema=SCHEMA)
    op.drop_table("processed_webhooks", schema=SCHEMA)
    op.drop_column("participants", "last_joined_at", schema=SCHEMA)
