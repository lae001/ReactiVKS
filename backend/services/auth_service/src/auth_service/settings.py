"""Настройки auth-service. Переменные окружения – docs/backend/auth-service.md, раздел «Конфигурация»."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from vks_common.config import ConfigurationError, DatabaseServiceSettings

__all__ = ["ALEMBIC_INI", "AuthSettings", "PasswordHashingSettings"]

# services/auth_service/alembic.ini – по нему сверяется версия схемы при старте.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class PasswordHashingSettings(DatabaseServiceSettings):
    """БД и стоимость Argon2id – все, что нужно CLI ``vks-auth``: ему не нужен ключ подписи."""

    service_name: str = "auth-service"

    # Параметры OWASP для Argon2id: 19 МиБ, 2 прохода, 1 поток. Вход – 100–300 мс, и параллельные входы не съедают
    # память контейнера (256 МБ). Хеш хранит свои параметры, поэтому их смена не ломает старые хеши.
    auth_argon2_time_cost: int = Field(default=2, ge=1)
    auth_argon2_memory_kib: int = Field(default=19456, ge=8)
    auth_argon2_parallelism: int = Field(default=1, ge=1)


class AuthSettings(PasswordHashingSettings):
    """Настройки работающего сервиса."""

    # Закрытый ключ RS256 (Docker secret). Значения по умолчанию нет: без ключа сервис не выпустит ни одного токена.
    jwt_private_key_path: Path
    # Публичный ключ прежней пары – публикуется в JWKS на время ротации.
    jwt_previous_public_key_path: Path | None = None

    auth_access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    auth_refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    auth_refresh_cookie_secure: bool = True
    auth_registration_enabled: bool = True

    @model_validator(mode="after")
    def _cookie_is_secure_in_production(self) -> Self:
        """Refresh-cookie без ``Secure`` в production ушла бы по открытому HTTP – это не настройка, а утечка."""
        if self.is_production and not self.auth_refresh_cookie_secure:
            raise ValueError("AUTH_REFRESH_COOKIE_SECURE=false запрещено при ENV=production")
        return self

    def read_private_key_pem(self) -> str:
        """Закрытый ключ – читается при сборке подписывающего и больше нигде не хранится."""
        return _read(self.jwt_private_key_path, "JWT_PRIVATE_KEY_PATH")

    def read_previous_public_key_pem(self) -> str | None:
        if self.jwt_previous_public_key_path is None:
            return None
        return _read(self.jwt_previous_public_key_path, "JWT_PREVIOUS_PUBLIC_KEY_PATH")


def _read(path: Path, variable: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"{variable}: файл {path} не читается: {error}") from error
