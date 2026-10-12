"""Помощники тестов: PostgreSQL в контейнере, изоляция транзакцией, клиент приложения.

Только для тестов: модуль импортирует testcontainers, который стоит в dev-зависимостях workspace.
"""

from vks_common.testing.database import apply_migrations, downgrade_migrations, isolated_session_factory
from vks_common.testing.http import app_client
from vks_common.testing.postgres import (
    SERVICE_ROLE_PASSWORDS,
    PostgresServer,
    docker_is_available,
    start_postgres,
)
from vks_common.testing.tokens import TokenFactory

__all__ = [
    "SERVICE_ROLE_PASSWORDS",
    "PostgresServer",
    "TokenFactory",
    "app_client",
    "apply_migrations",
    "docker_is_available",
    "downgrade_migrations",
    "isolated_session_factory",
    "start_postgres",
]
