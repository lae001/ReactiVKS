import pytest
from pydantic import SecretStr, ValidationError

from meeting_service.settings import MeetingSettings
from vks_common.config import ConfigurationError

DATABASE_URL = "postgresql+asyncpg://meeting_svc:secret@localhost:5432/vks"
SECRET = "dev-secret-change-me-0123456789abcdef"


def make_settings(**overrides: object) -> MeetingSettings:
    fields: dict[str, object] = {
        "database_url": DATABASE_URL,
        "livekit_api_key": "devkey",
        "livekit_api_secret": SecretStr(SECRET),
    }
    fields.update(overrides)
    return MeetingSettings(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def test_livekit_credentials_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    with pytest.raises(ConfigurationError, match="LIVEKIT_API_SECRET"):
        MeetingSettings.load()


def test_short_livekit_secret_is_refused() -> None:
    with pytest.raises(ValidationError, match="livekit_api_secret"):
        make_settings(livekit_api_secret=SecretStr("secret"))


def test_invite_url_points_to_lobby() -> None:
    settings = make_settings(public_base_url="https://vks.example.ru/")

    assert settings.invite_url("k3m7qx4tpa") == "https://vks.example.ru/j/k3m7qx4tpa"


def test_secret_is_masked_in_representation() -> None:
    assert SECRET not in repr(make_settings())
