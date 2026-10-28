"""Встречи, участники, журнал согласий и настройки организатора (схема meeting, database.md).

Таблицы outbox, processed_webhooks, livekit_sync_queue и blocked_users создаются миграциями задач, которые их
используют: событий meeting.events, вебхуков LiveKit, синхронизации согласия и проекции блокировок.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, INET

revision = "0001"
down_revision = None

SCHEMA = "meeting"


def upgrade() -> None:
    op.create_table(
        "organizer_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_enabled_default", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("analysis_fps_default", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("organizer_settings_pkey")),
        sa.CheckConstraint(
            "analysis_fps_default BETWEEN 2 AND 5",
            name=op.f("organizer_settings_analysis_fps_default_ck"),
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("owner_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("invite_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="scheduled", nullable=False),
        sa.Column("analysis_enabled", sa.Boolean(), nullable=False),
        sa.Column("analysis_fps", sa.SmallInteger(), nullable=False),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("meetings_pkey")),
        sa.UniqueConstraint("invite_code", name=op.f("meetings_invite_code_uk")),
        sa.CheckConstraint("invite_code ~ '^[a-z2-7]{10}$'", name=op.f("meetings_invite_code_ck")),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name=op.f("meetings_title_ck")),
        sa.CheckConstraint("char_length(owner_name) BETWEEN 1 AND 100", name=op.f("meetings_owner_name_ck")),
        sa.CheckConstraint(
            "status IN ('scheduled', 'active', 'ended', 'cancelled')",
            name=op.f("meetings_status_ck"),
        ),
        sa.CheckConstraint("analysis_fps BETWEEN 2 AND 5", name=op.f("meetings_analysis_fps_ck")),
        sa.CheckConstraint(
            "status NOT IN ('active', 'ended') OR started_at IS NOT NULL",
            name=op.f("meetings_started_at_ck"),
        ),
        sa.CheckConstraint("status <> 'ended' OR ended_at IS NOT NULL", name=op.f("meetings_ended_at_ck")),
        sa.CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('organizer', 'empty_timeout', 'admin')",
            name=op.f("meetings_end_reason_ck"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "meetings_owner_id_created_at_idx",
        "meetings",
        ["owner_id", sa.text("created_at DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "meetings_status_idx",
        "meetings",
        ["status"],
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('scheduled', 'active')"),
    )
    op.create_index(
        "meetings_title_idx",
        "meetings",
        ["title"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "meetings_deleted_at_idx",
        "meetings",
        ["deleted_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )

    op.create_table(
        "participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("consent_state", sa.Text(), nullable=False),
        sa.Column("participant_token_hash", BYTEA(), nullable=True),
        sa.Column("is_removed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("first_joined_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_left_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("participants_pkey")),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            [f"{SCHEMA}.meetings.id"],
            name=op.f("participants_meeting_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("participant_token_hash", name=op.f("participants_participant_token_hash_uk")),
        sa.CheckConstraint("char_length(display_name) BETWEEN 1 AND 64", name=op.f("participants_display_name_ck")),
        sa.CheckConstraint("role IN ('organizer', 'guest')", name=op.f("participants_role_ck")),
        sa.CheckConstraint(
            "consent_state IN ('granted', 'denied', 'revoked', 'not_required')",
            name=op.f("participants_consent_state_ck"),
        ),
        sa.CheckConstraint(
            "(role = 'organizer' AND user_id IS NOT NULL AND participant_token_hash IS NULL) OR "
            "(role = 'guest' AND user_id IS NULL AND participant_token_hash IS NOT NULL)",
            name=op.f("participants_identity_ck"),
        ),
        schema=SCHEMA,
    )
    op.create_index(op.f("participants_meeting_id_idx"), "participants", ["meeting_id"], schema=SCHEMA)
    op.create_index(
        "participants_meeting_id_user_id_uk",
        "participants",
        ["meeting_id", "user_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_table(
        "consents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("meeting_title", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("notice_version", sa.Text(), nullable=False),
        sa.Column("ip", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("consents_pkey")),
        sa.CheckConstraint("decision IN ('granted', 'denied', 'revoked')", name=op.f("consents_decision_ck")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("consents_participant_id_decided_at_idx"),
        "consents",
        ["participant_id", "decided_at"],
        schema=SCHEMA,
    )
    op.create_index(op.f("consents_meeting_id_idx"), "consents", ["meeting_id"], schema=SCHEMA)
    op.create_index(op.f("consents_decided_at_idx"), "consents", ["decided_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("consents", schema=SCHEMA)
    op.drop_table("participants", schema=SCHEMA)
    op.drop_table("meetings", schema=SCHEMA)
    op.drop_table("organizer_settings", schema=SCHEMA)
