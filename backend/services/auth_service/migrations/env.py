"""Окружение Alembic auth-service: все сложное – в vks_common.db.migrations."""

from auth_service.models import Base
from vks_common.db.migrations import run_migrations

run_migrations(target_metadata=Base.metadata, schema="auth")
