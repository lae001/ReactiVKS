from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from auth_service.domain.identifiers import RefreshTokenId, SessionFamilyId, UserId
from auth_service.domain.sessions import (
    RefreshOutcome,
    RefreshToken,
    build_access_claims,
    hash_refresh_token,
    judge_refresh,
)
from auth_service.domain.users import Role, User, UserStatus

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def make_token(**overrides: object) -> RefreshToken:
    fields: dict[str, object] = {
        "id": RefreshTokenId(uuid4()),
        "user_id": UserId(uuid4()),
        "family_id": SessionFamilyId(uuid4()),
        "token_hash": hash_refresh_token("token"),
        "expires_at": NOW + timedelta(days=30),
    }
    fields.update(overrides)
    return RefreshToken(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def test_access_claims_follow_the_contract() -> None:
    user = User(
        id=UserId(uuid4()),
        email="ivan@example.ru",
        password_hash="$argon2id$stub",
        display_name="Иван Петров",
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
        created_at=NOW,
    )
    token_id = uuid4()

    claims = build_access_claims(user=user, issuer="vks-auth", audience="vks", token_id=token_id, issued_at=NOW)

    assert claims == {
        "iss": "vks-auth",
        "aud": "vks",
        "sub": str(user.id),
        "role": "admin",
        "name": "Иван Петров",
        "iat": int(NOW.timestamp()),
        "exp": int(NOW.timestamp()) + 900,
        "jti": str(token_id),
    }


def test_refresh_token_hash_is_stable_sha256() -> None:
    assert hash_refresh_token("abc") == hash_refresh_token("abc")
    assert len(hash_refresh_token("abc")) == 32
    assert hash_refresh_token("abc") != hash_refresh_token("abd")


def test_fresh_token_is_neither_spent_nor_expired() -> None:
    token = make_token()

    assert not token.is_spent
    assert not token.is_expired(NOW)


def test_token_expires_exactly_at_its_deadline() -> None:
    token = make_token(expires_at=NOW)

    assert token.is_expired(NOW)
    assert not token.is_expired(NOW - timedelta(seconds=1))


def test_rotated_token_is_spent_and_points_to_successor() -> None:
    successor = RefreshTokenId(uuid4())

    rotated = make_token().rotated(successor=successor, now=NOW)

    assert rotated.is_spent
    assert rotated.replaced_by == successor
    assert rotated.revoked_at == NOW


def make_user(**overrides: object) -> User:
    fields: dict[str, object] = {
        "id": UserId(uuid4()),
        "email": "ivan@example.ru",
        "password_hash": "$argon2id$stub",
        "display_name": "Иван Петров",
        "role": Role.ORGANIZER,
        "status": UserStatus.ACTIVE,
        "created_at": NOW,
    }
    fields.update(overrides)
    return User(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def test_live_token_of_active_user_is_rotated() -> None:
    assert judge_refresh(make_token(), user=make_user(), now=NOW) is RefreshOutcome.ROTATE


def test_spent_token_revokes_family() -> None:
    spent = make_token().rotated(successor=RefreshTokenId(uuid4()), now=NOW)

    assert judge_refresh(spent, user=make_user(), now=NOW) is RefreshOutcome.REVOKE_FAMILY


def test_expired_token_is_rejected_without_touching_family() -> None:
    expired = make_token(expires_at=NOW - timedelta(seconds=1))

    assert judge_refresh(expired, user=make_user(), now=NOW) is RefreshOutcome.REJECT


@pytest.mark.parametrize(
    "user",
    [pytest.param(None, id="deleted"), pytest.param(make_user(status=UserStatus.BLOCKED), id="blocked")],
)
def test_token_of_missing_or_blocked_user_revokes_family(user: User | None) -> None:
    assert judge_refresh(make_token(), user=user, now=NOW) is RefreshOutcome.REVOKE_FAMILY
