from datetime import UTC, datetime
from uuid import uuid4

import pytest

from auth_service.domain.errors import InvalidDisplayName, InvalidEmail, UserBlocked
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import Role, User, UserStatus, normalize_display_name, normalize_email


def make_user(**overrides: object) -> User:
    fields: dict[str, object] = {
        "id": UserId(uuid4()),
        "email": "ivan@example.ru",
        "password_hash": "$argon2id$stub",
        "display_name": "Иван Петров",
        "role": Role.ORGANIZER,
        "status": UserStatus.ACTIVE,
        "created_at": datetime(2026, 10, 12, tzinfo=UTC),
    }
    fields.update(overrides)
    return User(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_email("  Ivan.Petrov@Example.RU ") == "ivan.petrov@example.ru"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("ivan", id="no-at"),
        pytest.param("ivan@localhost", id="no-dot-in-domain"),
        pytest.param("iv an@example.ru", id="space"),
        pytest.param("a@" + "b" * 250 + ".ru", id="too-long"),
    ],
)
def test_malformed_email_is_rejected_with_field(raw: str) -> None:
    with pytest.raises(InvalidEmail) as raised:
        normalize_email(raw)

    assert raised.value.field == "email"


def test_display_name_is_trimmed() -> None:
    assert normalize_display_name("  Анна  ") == "Анна"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 101])
def test_display_name_must_be_1_to_100_characters(raw: str) -> None:
    with pytest.raises(InvalidDisplayName):
        normalize_display_name(raw)


def test_blocked_status_means_blocked_user() -> None:
    assert make_user(status=UserStatus.BLOCKED).is_blocked
    assert not make_user().is_blocked


def test_renamed_user_keeps_everything_else() -> None:
    user = make_user()

    renamed = user.renamed("Анна")

    assert renamed.display_name == "Анна"
    assert renamed.id == user.id
    assert user.display_name == "Иван Петров"


def test_blocked_user_cannot_sign_in() -> None:
    make_user().ensure_can_sign_in()

    with pytest.raises(UserBlocked):
        make_user(status=UserStatus.BLOCKED).ensure_can_sign_in()
