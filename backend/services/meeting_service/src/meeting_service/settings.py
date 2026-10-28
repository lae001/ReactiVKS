"""Настройки meeting-service. Переменные окружения – docs/backend/meeting-service.md, раздел «Конфигурация»."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr

from vks_common.config import DatabaseServiceSettings

__all__ = ["ALEMBIC_INI", "MeetingSettings"]

# services/meeting_service/alembic.ini – по нему сверяется версия схемы при старте.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class MeetingSettings(DatabaseServiceSettings):
    service_name: str = "meeting-service"

    # Публичные ключи auth-service: access-токены организаторов сервис проверяет сам (ADR-005).
    jwks_url: str = "http://127.0.0.1:8001/api/v1/auth/.well-known/jwks.json"
    jwks_timeout_seconds: float = Field(default=2.0, gt=0)

    # Адрес фронтенда: из него строится ссылка-приглашение <PUBLIC_BASE_URL>/j/<код>.
    public_base_url: str = "http://localhost:5173"

    # Server API LiveKit (CreateRoom, DeleteRoom) – из внутренней сети.
    livekit_url: str = "http://localhost:7880"
    # Адрес сигнализации, который получает браузер участника.
    livekit_public_url: str = "ws://localhost:7880"
    # Ключ и секрет API – те же, что у сервера LiveKit. Значений по умолчанию нет: токен, подписанный не тем
    # секретом, LiveKit отвергнет только в браузере участника. LiveKit требует секрет не короче 32 символов.
    livekit_api_key: str = Field(min_length=1)
    livekit_api_secret: SecretStr = Field(min_length=32)
    # Срок токена участника (livekit-integration.md): встреча длиннее перезапрашивает его через rejoin.
    livekit_token_ttl_seconds: int = Field(default=6 * 3600, ge=60)
    # Таймаут вызова Server API (conventions.md, §5).
    livekit_timeout_seconds: float = Field(default=3.0, gt=0)

    # Брокер Kafka. Не задан – события копятся в outbox и уйдут, когда брокер появится в настройках.
    kafka_bootstrap_servers: str | None = None
    # Как часто релей outbox проверяет таблицу без сигнала о новой транзакции.
    outbox_poll_interval_seconds: float = Field(default=1.0, gt=0)

    def invite_url(self, invite_code: str) -> str:
        return f"{self.public_base_url.rstrip('/')}/j/{invite_code}"
