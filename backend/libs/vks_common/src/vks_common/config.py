"""Настройки сервисов из переменных окружения.

Каждый сервис наследует :class:`BaseServiceSettings` (или :class:`DatabaseServiceSettings`, если у него есть БД)
и добавляет свои поля. Имя поля и есть имя переменной: ``database_url`` читается из ``DATABASE_URL``.

Секрет можно передать файлом (Docker secrets): если задана переменная ``<ИМЯ>_FILE``, значение поля читается из
этого файла. Это единственное место проекта, где читается ``os.environ`` напрямую.

Настройки проверяются при старте: сервис с неполной конфигурацией не запускается (fail fast).
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import PostgresDsn, Secret, UrlConstraints, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

__all__ = [
    "BaseServiceSettings",
    "ConfigurationError",
    "DatabaseServiceSettings",
    "Environment",
    "FileSecretsSource",
    "LogLevel",
    "SecretPostgresUrl",
]

FILE_SUFFIX = "_FILE"


class Environment(StrEnum):
    """Окружение, в котором запущен сервис."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Порог корневого журнала."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


AsyncPostgresUrl = Annotated[
    PostgresDsn,
    UrlConstraints(host_required=True, allowed_schemes=["postgresql+asyncpg"]),
]

# Адрес БД содержит пароль, поэтому скрыт за Secret: str() и repr() настроек покажут маску.
SecretPostgresUrl = Secret[AsyncPostgresUrl]


class ConfigurationError(RuntimeError):
    """Окружение не описывает работоспособный сервис. Возбуждается при старте."""


class FileSecretsSource(PydanticBaseSettingsSource):
    """Источник настроек из файлов, названных переменными ``<ИМЯ>_FILE``.

    Стоит в цепочке после переменных окружения: явно заданная переменная ``<ИМЯ>`` важнее файла. Нечитаемый
    файл – ошибка конфигурации, а не молча пропущенное значение.
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[object, str, bool]:
        variable = f"{field_name.upper()}{FILE_SUFFIX}"
        path = os.environ.get(variable)
        if not path:
            return None, field_name, False
        try:
            # Перевод строки в конце файла – артефакт редактора, а не часть секрета.
            return Path(path).read_text(encoding="utf-8").rstrip("\r\n"), field_name, False
        except OSError as error:
            raise ConfigurationError(f"{variable}: файл {path} не читается: {error}") from error

    def __call__(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, _ = self.get_field_value(field, field_name)
            if value is not None:
                values[key] = value
        return values


class BaseServiceSettings(BaseSettings):
    """Настройки, которые есть у каждого сервиса."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", frozen=True)

    service_name: str
    service_version: str = "0.1.0"
    env: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO

    # --- проверка access-токенов (ADR-005) ---------------------------------------
    # Нужны каждому сервису, включая auth: он выпускает токены с этими iss и aud и проверяет их сам.
    jwt_issuer: str = "vks-auth"
    jwt_audience: str = "vks"
    # Только на расхождение часов между контейнерами. Не льготный период: access-токен нельзя отозвать,
    # и допустим он лишь потому, что истекает тогда, когда сказано.
    jwt_leeway_seconds: int = 5

    # Таймаут одной проверки зависимости в /ready (conventions.md, §10).
    ready_check_timeout_seconds: float = 1.0

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Аргументы конструктора → переменные окружения → файлы ``<ИМЯ>_FILE``.

        Файл ``.env`` не читается: для локального запуска есть ``uv run --env-file``, а неявный файл в рабочем
        каталоге – источник конфигурации, о котором оператор не знает.
        """
        return init_settings, env_settings, FileSecretsSource(settings_cls)

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @classmethod
    def load(cls) -> Self:
        """Прочитать настройки из окружения или упасть с понятным сообщением.

        pydantic называет поле; здесь оно переводится в имя переменной, которую на самом деле задает оператор.
        """
        try:
            return cls()
        except ValidationError as error:
            raise ConfigurationError(cls._describe(error)) from error

    @classmethod
    def _describe(cls, error: ValidationError) -> str:
        lines = [f"конфигурация {cls.__name__} неполна или неверна:"]
        for problem in error.errors(include_input=False):
            location = problem["loc"]
            variable = str(location[0]).upper() if location else "<настройки>"
            lines.append(f"  {variable}: {problem['msg']}")
        return "\n".join(lines)


class DatabaseServiceSettings(BaseServiceSettings):
    """Настройки сервиса со своей схемой PostgreSQL (auth, meeting, analytics)."""

    # У адреса нет значения по умолчанию: сервис, молча подключившийся не к той базе, хуже упавшего.
    database_url: SecretPostgresUrl
    # Пул 5–10 соединений на сервис (conventions.md, §8).
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: float = 5.0

    @property
    def database_url_value(self) -> str:
        """Адрес БД открытым текстом – только для передачи драйверу."""
        return str(self.database_url.get_secret_value())
