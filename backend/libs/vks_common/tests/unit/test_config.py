from pathlib import Path

import pytest

from vks_common.config import (
    ConfigurationError,
    DatabaseServiceSettings,
    Environment,
)

DATABASE_URL = "postgresql+asyncpg://auth_svc:secret@localhost:5432/vks"


class ExampleSettings(DatabaseServiceSettings):
    service_name: str = "example"


def test_settings_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("ENV", "production")

    settings = ExampleSettings.load()

    assert settings.database_url_value == DATABASE_URL
    assert settings.env is Environment.PRODUCTION
    assert settings.is_production


def test_secret_is_read_from_file_named_by_file_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "database_url"
    secret_file.write_text(DATABASE_URL + "\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_FILE", str(secret_file))

    settings = ExampleSettings.load()

    assert settings.database_url_value == DATABASE_URL


def test_environment_variable_wins_over_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "database_url"
    secret_file.write_text("postgresql+asyncpg://other:x@db:5432/other", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL_FILE", str(secret_file))

    settings = ExampleSettings.load()

    assert settings.database_url_value == DATABASE_URL


def test_unreadable_secret_file_is_configuration_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_FILE", str(tmp_path / "missing"))

    with pytest.raises(ConfigurationError, match="DATABASE_URL_FILE"):
        ExampleSettings.load()


def test_missing_required_setting_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        ExampleSettings.load()


def test_database_url_is_masked_in_repr() -> None:
    settings = ExampleSettings(database_url=DATABASE_URL)

    assert "secret" not in repr(settings)


def test_only_asyncpg_urls_are_accepted() -> None:
    with pytest.raises(ValueError, match="postgresql\\+asyncpg"):
        ExampleSettings(database_url="postgresql://auth_svc:secret@localhost:5432/vks")
