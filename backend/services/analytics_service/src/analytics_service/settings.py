"""Окружение analytics-service."""

from pathlib import Path

from vks_common.config import DatabaseServiceSettings

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class AnalyticsSettings(DatabaseServiceSettings):
    service_name: str = "analytics-service"
    jwks_url: str = "http://127.0.0.1:8001/api/v1/auth/.well-known/jwks.json"
    kafka_bootstrap_servers: str = "127.0.0.1:9092"
