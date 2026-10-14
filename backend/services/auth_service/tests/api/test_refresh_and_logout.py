from collections.abc import Awaitable, Callable
from datetime import timedelta
from http.cookies import SimpleCookie

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.users import User
from vks_common.clock import FixedClock

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
PASSWORD = "correct-horse-7"

UserFactory = Callable[..., Awaitable[User]]


def cookie_of(response: httpx.Response) -> SimpleCookie:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


async def sign_in(client: httpx.AsyncClient, user: User) -> str:
    """Войти и вернуть refresh-токен. Хранилище cookie клиента очищается: каждый тест передает токен явно."""
    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    client.cookies.clear()
    return cookie_of(response)["vks_refresh"].value


async def refresh(client: httpx.AsyncClient, token: str) -> httpx.Response:
    response = await client.post(REFRESH, headers={"Cookie": f"vks_refresh={token}"})
    client.cookies.clear()
    return response


async def test_refresh_rotates_the_pair(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    token = await sign_in(client, user)

    response = await refresh(client, token)

    body = response.json()
    assert response.status_code == 200
    assert body["user"]["id"] == str(user.id)
    assert body["access_token"]
    new_token = cookie_of(response)["vks_refresh"].value
    assert new_token != token
    assert cookie_of(response)["vks_refresh"]["path"] == "/api/v1/auth"


async def test_successor_token_keeps_working(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    token = await sign_in(client, await make_user())
    second = cookie_of(await refresh(client, token))["vks_refresh"].value

    response = await refresh(client, second)

    assert response.status_code == 200


async def test_reused_token_revokes_whole_family(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    token = await sign_in(client, await make_user())
    successor = cookie_of(await refresh(client, token))["vks_refresh"].value

    reuse = await refresh(client, token)
    after_reuse = await refresh(client, successor)

    assert reuse.status_code == 401
    assert reuse.json()["code"] == "unauthorized"
    assert after_reuse.status_code == 401


async def test_reuse_on_one_device_keeps_other_devices_signed_in(
    client: httpx.AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user()
    laptop = await sign_in(client, user)
    phone = await sign_in(client, user)
    await refresh(client, laptop)

    await refresh(client, laptop)

    assert (await refresh(client, phone)).status_code == 200


async def test_refresh_without_cookie_is_401(client: httpx.AsyncClient) -> None:
    response = await client.post(REFRESH)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_unknown_token_is_401_and_cookie_is_cleared(client: httpx.AsyncClient) -> None:
    response = await refresh(client, "forged-token")

    assert response.status_code == 401
    cleared = cookie_of(response)["vks_refresh"]
    assert cleared.value == ""
    assert cleared["max-age"] == "0"
    assert cleared["path"] == "/api/v1/auth"


async def test_expired_token_is_401(client: httpx.AsyncClient, clock: FixedClock, make_user: UserFactory) -> None:
    token = await sign_in(client, await make_user())
    clock.advance(timedelta(days=30, seconds=1))

    response = await refresh(client, token)

    assert response.status_code == 401


async def test_blocked_user_cannot_refresh(
    client: httpx.AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    user = await make_user()
    token = await sign_in(client, user)
    await session.execute(text("UPDATE auth.users SET status = 'blocked' WHERE id = :id"), {"id": user.id})
    await session.commit()

    response = await refresh(client, token)

    assert response.status_code == 401


async def test_logout_revokes_session_and_clears_cookie(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    token = await sign_in(client, await make_user())

    response = await client.post(LOGOUT, headers={"Cookie": f"vks_refresh={token}"})

    assert response.status_code == 204
    assert cookie_of(response)["vks_refresh"]["max-age"] == "0"
    assert (await refresh(client, token)).status_code == 401


async def test_logout_without_cookie_is_still_204(client: httpx.AsyncClient) -> None:
    response = await client.post(LOGOUT)

    assert response.status_code == 204


async def test_logout_is_repeatable(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    token = await sign_in(client, await make_user())
    await client.post(LOGOUT, headers={"Cookie": f"vks_refresh={token}"})

    response = await client.post(LOGOUT, headers={"Cookie": f"vks_refresh={token}"})

    assert response.status_code == 204
