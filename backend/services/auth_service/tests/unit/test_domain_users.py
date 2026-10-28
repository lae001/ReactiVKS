from datetime import UTC, datetime
from uuid import uuid4

import pytest

from auth_service.domain.errors import InvalidDisplayName, InvalidEmail, LastAdmin, UserBlocked
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import (
    InvalidCursor,
    Role,
    User,
    UserCursor,
    UserStatus,
    ensure_admin_remains,
    normalize_display_name,
    normalize_email,
)


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


def test_administered_without_changes_returns_same_user() -> None:
    user = make_user()

    assert user.administered(status=UserStatus.ACTIVE, role=None) is user


def test_administered_changes_status_and_role() -> None:
    user = make_user().administered(status=UserStatus.BLOCKED, role=Role.ADMIN)

    assert (user.status, user.role) == (UserStatus.BLOCKED, Role.ADMIN)


@pytest.mark.parametrize(
    "after",
    [
        pytest.param({"status": UserStatus.BLOCKED}, id="block"),
        pytest.param({"role": Role.ORGANIZER}, id="demote"),
        pytest.param(None, id="delete"),
    ],
)
def test_administrator_cannot_act_on_self(after: dict[str, object] | None) -> None:
    admin = make_user(role=Role.ADMIN)

    with pytest.raises(LastAdmin):
        ensure_admin_remains(
            actor_id=admin.id,
            before=admin,
            after=admin.administered(**after) if after is not None else None,  # type: ignore[arg-type]
            active_admins=2,
        )


def test_last_active_admin_cannot_be_lost() -> None:
    admin = make_user(role=Role.ADMIN)

    with pytest.raises(LastAdmin):
        ensure_admin_remains(
            actor_id=UserId(uuid4()),
            before=admin,
            after=admin.administered(status=UserStatus.BLOCKED),
            active_admins=1,
        )


def test_admin_can_be_demoted_while_another_remains() -> None:
    admin = make_user(role=Role.ADMIN)

    ensure_admin_remains(
        actor_id=UserId(uuid4()), before=admin, after=admin.administered(role=Role.ORGANIZER), active_admins=2
    )


def test_organizer_can_be_blocked_by_the_only_admin() -> None:
    organizer = make_user()

    ensure_admin_remains(
        actor_id=UserId(uuid4()),
        before=organizer,
        after=organizer.administered(status=UserStatus.BLOCKED),
        active_admins=1,
    )


def test_user_cursor_survives_round_trip() -> None:
    cursor = UserCursor(created_at=datetime(2026, 10, 12, tzinfo=UTC), user_id=uuid4())

    assert UserCursor.decode(cursor.encode()) == cursor


@pytest.mark.parametrize("value", ["not-a-cursor", "e30"])
def test_foreign_user_cursor_is_refused(value: str) -> None:
    with pytest.raises(InvalidCursor):
        UserCursor.decode(value)
