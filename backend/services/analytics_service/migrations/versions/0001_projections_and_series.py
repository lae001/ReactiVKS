"""Проекции встреч, согласия и посекундные ряды (EMO-86)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None

PROBABILITIES = ('p_angry', 'p_disgust', 'p_fear', 'p_happy', 'p_sad', 'p_surprise', 'p_neutral')


def upgrade() -> None:
    op.create_table('deleted_meetings',
    sa.Column('meeting_id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('meeting_id', name=op.f('deleted_meetings_pkey')),
    schema='analytics'
    )
    op.create_table('deleted_owners',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('owner_id', name=op.f('deleted_owners_pkey')),
    schema='analytics'
    )
    op.create_table('emotion_series',
    sa.Column('meeting_id', sa.Uuid(), nullable=False),
    sa.Column('participant_id', sa.Uuid(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('samples', sa.SmallInteger(), nullable=False),
    sa.Column('face_samples', sa.SmallInteger(), nullable=False),
    sa.Column('p_angry', sa.REAL(), nullable=True),
    sa.Column('p_disgust', sa.REAL(), nullable=True),
    sa.Column('p_fear', sa.REAL(), nullable=True),
    sa.Column('p_happy', sa.REAL(), nullable=True),
    sa.Column('p_sad', sa.REAL(), nullable=True),
    sa.Column('p_surprise', sa.REAL(), nullable=True),
    sa.Column('p_neutral', sa.REAL(), nullable=True),
    sa.Column('model_version', sa.Text(), nullable=False),
    sa.CheckConstraint(
        "(face_samples = 0 AND " + " AND ".join(f"{label} IS NULL" for label in PROBABILITIES)
        + ") OR (face_samples > 0 AND "
        + " AND ".join(f"({label} IS NOT NULL AND {label} BETWEEN 0 AND 1)" for label in PROBABILITIES) + ")",
        name=op.f("emotion_series_probs_ck"),
    ),
    sa.CheckConstraint('samples > 0 AND face_samples BETWEEN 0 AND samples', name=op.f('emotion_series_samples_ck')),
    sa.PrimaryKeyConstraint('meeting_id', 'participant_id', 'ts', name=op.f('emotion_series_pkey')),
    schema='analytics'
    )
    op.create_index('emotion_series_meeting_ts_idx', 'emotion_series', ['meeting_id', 'ts'], unique=False, schema='analytics')
    op.create_table('meeting_projection',
    sa.Column('meeting_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('analysis_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('scheduled','active','ended','cancelled')", name=op.f('meeting_projection_status_ck')),
    sa.PrimaryKeyConstraint('meeting_id', name=op.f('meeting_projection_pkey')),
    schema='analytics'
    )
    op.create_index('meeting_projection_ended_idx', 'meeting_projection', ['ended_at'], unique=False, schema='analytics')
    op.create_index('meeting_projection_owner_idx', 'meeting_projection', ['owner_id'], unique=False, schema='analytics')
    op.create_table('outbox',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('topic', sa.Text(), nullable=False),
    sa.Column('event_key', sa.Text(), nullable=False),
    sa.Column('event_type', sa.Text(), nullable=False),
    sa.Column('envelope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('outbox_pkey')),
    sa.UniqueConstraint('event_id', name=op.f('outbox_event_id_uk')),
    schema='analytics'
    )
    op.create_index('outbox_unpublished_idx', 'outbox', ['id'], unique=False, schema='analytics', postgresql_where=sa.text('published_at IS NULL'))
    op.create_table('sample_offsets',
    sa.Column('partition', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('next_offset', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('partition', name=op.f('sample_offsets_pkey')),
    schema='analytics'
    )
    op.create_table('participant_projection',
    sa.Column('participant_id', sa.Uuid(), nullable=False),
    sa.Column('meeting_id', sa.Uuid(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('consent_state', sa.Text(), nullable=False),
    sa.Column('consent_decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['analytics.meeting_projection.meeting_id'], name=op.f('participant_projection_meeting_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('participant_id', name=op.f('participant_projection_pkey')),
    schema='analytics'
    )
    op.create_index('participant_projection_meeting_idx', 'participant_projection', ['meeting_id'], unique=False, schema='analytics')
    op.create_table('consent_history',
    sa.Column('participant_id', sa.Uuid(), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_granted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['participant_id'], ['analytics.participant_projection.participant_id'], name=op.f('consent_history_participant_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('participant_id', 'decided_at', name=op.f('consent_history_pkey')),
    schema='analytics'
    )


def downgrade() -> None:
    op.drop_table('consent_history', schema='analytics')
    op.drop_index('participant_projection_meeting_idx', table_name='participant_projection', schema='analytics')
    op.drop_table('participant_projection', schema='analytics')
    op.drop_table('sample_offsets', schema='analytics')
    op.drop_index('outbox_unpublished_idx', table_name='outbox', schema='analytics', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_table('outbox', schema='analytics')
    op.drop_index('meeting_projection_owner_idx', table_name='meeting_projection', schema='analytics')
    op.drop_index('meeting_projection_ended_idx', table_name='meeting_projection', schema='analytics')
    op.drop_table('meeting_projection', schema='analytics')
    op.drop_index('emotion_series_meeting_ts_idx', table_name='emotion_series', schema='analytics')
    op.drop_table('emotion_series', schema='analytics')
    op.drop_table('deleted_owners', schema='analytics')
    op.drop_table('deleted_meetings', schema='analytics')
