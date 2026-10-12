import pytest

from auth_service.domain.errors import WeakPassword
from auth_service.domain.passwords import check_password_policy


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("correct8", id="minimum-length"),
        pytest.param("Пароль2026", id="cyrillic"),
        pytest.param("with inner space 1", id="inner-space"),
        pytest.param("a1" * 64, id="maximum-length"),
    ],
)
def test_acceptable_password_passes(password: str) -> None:
    check_password_policy(password)


@pytest.mark.parametrize(
    ("password", "rule"),
    [
        pytest.param("short1a", "at least 8", id="too-short"),
        pytest.param("a1" * 64 + "x", "at most 128", id="too-long"),
        pytest.param(" leading1", "whitespace", id="leading-space"),
        pytest.param("trailing1 ", "whitespace", id="trailing-space"),
        pytest.param("12345678", "letter", id="digits-only"),
        pytest.param("password", "digit", id="letters-only"),
    ],
)
def test_weak_password_names_the_rule(password: str, rule: str) -> None:
    with pytest.raises(WeakPassword, match=rule) as raised:
        check_password_policy(password)

    assert password not in raised.value.detail
    assert raised.value.field == "password"


def test_field_name_is_configurable_for_password_change() -> None:
    with pytest.raises(WeakPassword) as raised:
        check_password_policy("short", field="new_password")

    assert raised.value.field == "new_password"
