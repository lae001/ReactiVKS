"""Окружение realtime-service."""

from socket import gethostname

from pydantic import Field, SecretStr

from vks_common.config import BaseServiceSettings


class RealtimeSettings(BaseServiceSettings):
    service_name: str = "realtime-service"
    service_token: SecretStr = Field(min_length=32)
    jwks_url: str = "http://127.0.0.1:8001/api/v1/auth/.well-known/jwks.json"
    meeting_url: str = "http://127.0.0.1:8002"
    redis_url: str | None = "redis://127.0.0.1:6379/0"
    redis_password: SecretStr | None = None
    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    instance: str = Field(default_factory=gethostname, min_length=1)
