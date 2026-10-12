from pathlib import Path

import pytest
from pydantic import ValidationError

from auth_service.settings import AuthSettings
from vks_common.config import ConfigurationError, Environment

DATABASE_URL = "postgresql+asyncpg://auth_svc:secret@localhost:5432/vks"


def make_settings(**overrides: object) -> AuthSettings:
    fields: dict[str, object] = {"database_url": DATABASE_URL, "jwt_private_key_path": Path("missing.pem")}
    fields.update(overrides)
    return AuthSettings(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def test_defaults_follow_the_contract() -> None:
    settings = make_settings()

    assert settings.auth_access_token_ttl_seconds == 900
    assert settings.auth_refresh_token_ttl_days == 30
    assert settings.auth_refresh_cookie_secure
    assert settings.auth_registration_enabled


def test_signing_key_path_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.delenv("JWT_PRIVATE_KEY_PATH", raising=False)

    with pytest.raises(ConfigurationError, match="JWT_PRIVATE_KEY_PATH"):
        AuthSettings.load()


def test_insecure_cookie_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="AUTH_REFRESH_COOKIE_SECURE"):
        make_settings(env=Environment.PRODUCTION, auth_refresh_cookie_secure=False)


def test_insecure_cookie_is_allowed_in_development() -> None:
    settings = make_settings(env=Environment.DEVELOPMENT, auth_refresh_cookie_secure=False)

    assert not settings.auth_refresh_cookie_secure


def test_unreadable_key_file_is_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="JWT_PRIVATE_KEY_PATH"):
        make_settings().read_private_key_pem()


def test_previous_key_is_optional() -> None:
    assert make_settings().read_previous_public_key_pem() is None
