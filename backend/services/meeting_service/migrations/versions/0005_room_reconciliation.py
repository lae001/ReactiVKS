"""Время подтвержденного отсутствия комнаты LiveKit (EMO-102)."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.add_column("meetings", sa.Column("room_missing_since", sa.DateTime(timezone=True)), schema="meeting")


def downgrade() -> None:
    op.drop_column("meetings", "room_missing_since", schema="meeting")
