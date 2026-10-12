"""Окружение Alembic примера: таблица notes в схеме auth (роль auth_svc)."""

from sqlalchemy import MetaData

from vks_common.db.migrations import run_migrations

run_migrations(target_metadata=MetaData(schema="auth"), schema="auth")
