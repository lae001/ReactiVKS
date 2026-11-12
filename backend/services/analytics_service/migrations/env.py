"""Окружение Alembic analytics-service: все сложное – в vks_common.db.migrations."""

from analytics_service.models import metadata
from vks_common.db.migrations import run_migrations

run_migrations(target_metadata=metadata, schema="analytics")
