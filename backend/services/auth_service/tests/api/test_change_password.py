from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie

import httpx
import pytest

from auth_service.domain.users import User

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-7"
NEW_PASSWORD = "battery-staple-9"
CHANGE = "/api/v1/users/me/password"

UserFactory = Callable[..., Awaitable[User]]


async def sign_in(client: httpx.AsyncClient, user: User, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})


async def bearer(client: httpx.AsyncClient, user: User) -> dict[str, str]:
    response = await sign_in(client, user)
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_new_password_replaces_old_one(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = await bearer(client, user)

    response = await client.post(
        CHANGE, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}, headers=headers
    )

    assert response.status_code == 204
    assert (await sign_in(client, user, NEW_PASSWORD)).status_code == 200
    assert (await sign_in(client, user, PASSWORD)).status_code == 401


async def test_password_change_ends_all_sessions(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    other_device = SimpleCookie((await sign_in(client, user)).headers["set-cookie"])["vks_refresh"].value
    headers = await bearer(client, user)

    await client.post(CHANGE, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}, headers=headers)

    client.cookies.clear()
    refreshed = await client.post("/api/v1/auth/refresh", headers={"Cookie": f"vks_refresh={other_device}"})
    assert refreshed.status_code == 401


async def test_wrong_current_password_is_401(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = await bearer(client, user)

    response = await client.post(
        CHANGE, json={"current_password": "wrong-horse-7", "new_password": NEW_PASSWORD}, headers=headers
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert (await sign_in(client, user, PASSWORD)).status_code == 200


@pytest.mark.parametrize("new_password", ["short1", "lettersonly", "1234567890", " padded-pass-1"])
async def test_weak_new_password_is_422(client: httpx.AsyncClient, make_user: UserFactory, new_password: str) -> None:
    headers = await bearer(client, await make_user())

    response = await client.post(
        CHANGE, json={"current_password": PASSWORD, "new_password": new_password}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "new_password"]


async def test_password_change_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.post(CHANGE, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
