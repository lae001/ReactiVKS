from collections.abc import Awaitable, Callable
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.users import Role, User
from vks_common.testing import TokenFactory

pytestmark = pytest.mark.integration

ME = "/api/v1/users/me"
PASSWORD = "correct-horse-7"

UserFactory = Callable[..., Awaitable[User]]


async def bearer(client: httpx.AsyncClient, user: User) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_profile_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_profile_of_signed_in_user(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(email="anna@example.ru", display_name="Анна", role=Role.ADMIN)

    response = await client.get(ME, headers=await bearer(client, user))

    assert response.json() == {"id": str(user.id), "email": "anna@example.ru", "display_name": "Анна", "role": "admin"}


async def test_token_signed_by_foreign_key_is_401(client: httpx.AsyncClient) -> None:
    forged = TokenFactory().issue(user_id=uuid4())

    response = await client.get(ME, headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


async def test_deleted_account_with_live_token_is_401(
    client: httpx.AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    user = await make_user()
    headers = await bearer(client, user)
    await session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": user.id})
    await session.commit()

    response = await client.get(ME, headers=headers)

    assert response.status_code == 401


async def test_display_name_is_changed_and_trimmed(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = await bearer(client, user)

    response = await client.patch(ME, json={"display_name": "  Анна Смирнова "}, headers=headers)

    assert response.status_code == 200
    assert response.json()["display_name"] == "Анна Смирнова"
    assert (await client.get(ME, headers=headers)).json()["display_name"] == "Анна Смирнова"


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 101])
async def test_invalid_display_name_is_422(
    client: httpx.AsyncClient, make_user: UserFactory, display_name: str
) -> None:
    headers = await bearer(client, await make_user())

    response = await client.patch(ME, json={"display_name": display_name}, headers=headers)

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "display_name"]


async def test_rename_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.patch(ME, json={"display_name": "Анна"})

    assert response.status_code == 401
