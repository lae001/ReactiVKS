from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.domain.users import Role, User, UserStatus
from vks_common.auth import TokenVerifier

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
PASSWORD = "correct-horse-7"

UserFactory = Callable[..., Awaitable[User]]


class CountingHasher:
    """Настоящий Argon2 плюс счетчик фиктивных проверок."""

    def __init__(self, inner: Argon2Hasher) -> None:
        self._inner = inner
        self.dummy_verifications = 0

    def hash(self, password: str) -> str:
        return self._inner.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._inner.verify(password, password_hash)

    def verify_dummy(self) -> None:
        self.dummy_verifications += 1
        self._inner.verify_dummy()


def refresh_cookie(response: httpx.Response) -> SimpleCookie:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


async def test_login_returns_access_token_and_user(
    client: httpx.AsyncClient, app: FastAPI, make_user: UserFactory
) -> None:
    user = await make_user(email="ivan@example.ru", role=Role.ADMIN)

    response = await client.post(LOGIN, json={"email": "Ivan@Example.ru", "password": PASSWORD})

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["user"] == {
        "id": str(user.id),
        "email": "ivan@example.ru",
        "display_name": "Иван Петров",
        "role": "admin",
    }
    verifier: TokenVerifier = app.state.token_verifier
    claims = await verifier.verify(body["access_token"])
    assert (claims.user_id, claims.role, claims.name) == (user.id, "admin", "Иван Петров")


async def test_refresh_cookie_follows_the_contract(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()

    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    morsel = refresh_cookie(response)["vks_refresh"]
    assert len(morsel.value) == 43
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"] == "strict"
    assert morsel["path"] == "/api/v1/auth"
    assert morsel["max-age"] == str(30 * 24 * 3600)


async def test_only_hash_of_refresh_token_is_stored(
    client: httpx.AsyncClient,
    session: AsyncSession,
    make_user: UserFactory,
) -> None:
    user = await make_user()

    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    token = refresh_cookie(response)["vks_refresh"].value
    rows = (
        await session.execute(
            text("SELECT token_hash, user_agent FROM auth.refresh_tokens WHERE user_id = :id"), {"id": user.id}
        )
    ).all()
    assert len(rows) == 1
    assert token.encode() not in rows[0].token_hash
    assert rows[0].user_agent is not None


async def test_login_moment_is_recorded(
    client: httpx.AsyncClient,
    session: AsyncSession,
    make_user: UserFactory,
) -> None:
    user = await make_user()

    await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    result = await session.execute(text("SELECT last_login_at FROM auth.users WHERE id = :id"), {"id": user.id})
    assert result.scalar_one() is not None


async def test_wrong_password_and_unknown_email_answer_identically(
    client: httpx.AsyncClient,
    make_user: UserFactory,
) -> None:
    user = await make_user()

    wrong_password = await client.post(LOGIN, json={"email": user.email, "password": "wrong-password-1"})
    unknown_email = await client.post(LOGIN, json={"email": "nobody@example.ru", "password": PASSWORD})
    malformed_email = await client.post(LOGIN, json={"email": "not-an-email", "password": PASSWORD})

    assert wrong_password.status_code == unknown_email.status_code == malformed_email.status_code == 401
    bodies = [
        {key: value for key, value in r.json().items() if key != "request_id"}
        for r in (wrong_password, unknown_email, malformed_email)
    ]
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["code"] == "invalid_credentials"
    assert "set-cookie" not in wrong_password.headers


async def test_unknown_email_spends_a_dummy_password_check(
    client: httpx.AsyncClient,
    app: FastAPI,
    hasher: Argon2Hasher,
) -> None:
    counting = CountingHasher(hasher)
    app.state.password_hasher = counting

    await client.post(LOGIN, json={"email": "nobody@example.ru", "password": PASSWORD})

    assert counting.dummy_verifications == 1


async def test_blocked_user_with_correct_password_is_403(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(status=UserStatus.BLOCKED)

    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["code"] == "user_blocked"


async def test_blocked_user_with_wrong_password_learns_nothing(
    client: httpx.AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user(status=UserStatus.BLOCKED)

    response = await client.post(LOGIN, json={"email": user.email, "password": "wrong-password-1"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_missing_password_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(LOGIN, json={"email": "ivan@example.ru"})

    assert response.status_code == 422
