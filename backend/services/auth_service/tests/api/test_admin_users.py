"""Администрирование учетных записей: ``/api/v1/admin/users`` и события user.events (EMO-67)."""

import json
from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.users import Role, User, UserStatus
from vks_contracts import parse_event
from vks_contracts.user_events import UserBlocked

pytestmark = pytest.mark.integration

USERS = "/api/v1/admin/users"
PASSWORD = "correct-horse-7"

UserFactory = Callable[..., Awaitable[User]]


async def sign_in(client: httpx.AsyncClient, user: User) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})


async def bearer(client: httpx.AsyncClient, user: User) -> dict[str, str]:
    response = await sign_in(client, user)
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def admin(make_user: UserFactory) -> User:
    return await make_user(email="admin@example.ru", display_name="Администратор", role=Role.ADMIN)


async def events(session: AsyncSession, user: User) -> list[tuple[str, str]]:
    rows = await session.execute(
        text("SELECT topic, envelope FROM auth.outbox WHERE event_key = :key ORDER BY id"), {"key": str(user.id)}
    )
    return [(topic, parse_event(json.dumps(envelope)).envelope.type) for topic, envelope in rows]


async def test_admin_lists_users_newest_first_with_status(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User
) -> None:
    blocked = await make_user(email="blocked@example.ru", status=UserStatus.BLOCKED)

    response = await client.get(USERS, headers=await bearer(client, admin))

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["email"] for item in items} == {"admin@example.ru", "blocked@example.ru"}
    assert next(item for item in items if item["id"] == str(blocked.id))["status"] == "blocked"
    assert set(items[0]) == {"id", "email", "display_name", "role", "status", "created_at", "last_login_at"}


async def test_list_is_filtered_by_text_and_status(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User
) -> None:
    await make_user(email="anna@example.ru", display_name="Анна")
    await make_user(email="boris@example.ru", display_name="Борис", status=UserStatus.BLOCKED)
    headers = await bearer(client, admin)

    by_name = await client.get(USERS, params={"q": "анн"}, headers=headers)
    by_status = await client.get(USERS, params={"status": "blocked"}, headers=headers)

    assert [item["email"] for item in by_name.json()["items"]] == ["anna@example.ru"]
    assert [item["email"] for item in by_status.json()["items"]] == ["boris@example.ru"]


async def test_list_is_paginated_by_cursor(client: httpx.AsyncClient, make_user: UserFactory, admin: User) -> None:
    for index in range(3):
        await make_user(email=f"user{index}@example.ru")
    headers = await bearer(client, admin)

    first = (await client.get(USERS, params={"limit": 3}, headers=headers)).json()
    second = (await client.get(USERS, params={"limit": 3, "cursor": first["next_cursor"]}, headers=headers)).json()

    emails = [item["email"] for page in (first, second) for item in page["items"]]
    assert sorted(emails) == ["admin@example.ru", "user0@example.ru", "user1@example.ru", "user2@example.ru"]
    assert second["next_cursor"] is None


async def test_blocking_ends_sessions_and_publishes_event(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User, session: AsyncSession
) -> None:
    user = await make_user()
    device = SimpleCookie((await sign_in(client, user)).headers["set-cookie"])["vks_refresh"].value
    client.cookies.clear()

    response = await client.patch(f"{USERS}/{user.id}", json={"status": "blocked"}, headers=await bearer(client, admin))

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    refreshed = await client.post("/api/v1/auth/refresh", headers={"Cookie": f"vks_refresh={device}"})
    assert refreshed.status_code == 401
    assert (await sign_in(client, user)).json()["code"] == "user_blocked"
    assert await events(session, user) == [("user.events", "user.blocked")]


async def test_unblocking_publishes_event_and_lets_user_in(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User, session: AsyncSession
) -> None:
    user = await make_user(status=UserStatus.BLOCKED)

    await client.patch(f"{USERS}/{user.id}", json={"status": "active"}, headers=await bearer(client, admin))

    assert (await sign_in(client, user)).status_code == 200
    assert await events(session, user) == [("user.events", "user.unblocked")]


async def test_repeated_block_changes_nothing(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User, session: AsyncSession
) -> None:
    user = await make_user()
    headers = await bearer(client, admin)

    await client.patch(f"{USERS}/{user.id}", json={"status": "blocked"}, headers=headers)
    repeated = await client.patch(f"{USERS}/{user.id}", json={"status": "blocked"}, headers=headers)

    assert repeated.status_code == 200
    assert await events(session, user) == [("user.events", "user.blocked")]


async def test_role_change_is_returned(client: httpx.AsyncClient, make_user: UserFactory, admin: User) -> None:
    user = await make_user()

    response = await client.patch(f"{USERS}/{user.id}", json={"role": "admin"}, headers=await bearer(client, admin))

    assert response.json()["role"] == "admin"


@pytest.mark.parametrize("body", [{"status": "blocked"}, {"role": "organizer"}])
async def test_admin_cannot_block_or_demote_self(client: httpx.AsyncClient, admin: User, body: dict[str, str]) -> None:
    response = await client.patch(f"{USERS}/{admin.id}", json=body, headers=await bearer(client, admin))

    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"


async def test_admin_cannot_delete_self(client: httpx.AsyncClient, admin: User, session: AsyncSession) -> None:
    response = await client.delete(f"{USERS}/{admin.id}", headers=await bearer(client, admin))

    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"
    assert await events(session, admin) == []


async def test_deleted_user_is_gone_and_event_published(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User, session: AsyncSession
) -> None:
    user = await make_user()
    headers = await bearer(client, admin)

    response = await client.delete(f"{USERS}/{user.id}", headers=headers)

    assert response.status_code == 204
    assert (await sign_in(client, user)).json()["code"] == "invalid_credentials"
    assert (await client.delete(f"{USERS}/{user.id}", headers=headers)).status_code == 404
    assert await events(session, user) == [("user.events", "user.deleted")]


async def test_user_events_are_keyed_by_user(
    client: httpx.AsyncClient, make_user: UserFactory, admin: User, session: AsyncSession
) -> None:
    user = await make_user()
    await client.patch(f"{USERS}/{user.id}", json={"status": "blocked"}, headers=await bearer(client, admin))

    envelope = (
        await session.execute(text("SELECT envelope FROM auth.outbox WHERE event_key = :key"), {"key": str(user.id)})
    ).scalar_one()

    parsed = parse_event(json.dumps(envelope))
    assert parsed.envelope.producer == "auth-service"
    assert parsed.payload == UserBlocked(user_id=user.id)


async def test_unknown_user_is_404(client: httpx.AsyncClient, admin: User) -> None:
    headers = await bearer(client, admin)

    patched = await client.patch(f"{USERS}/{uuid4()}", json={"status": "blocked"}, headers=headers)
    deleted = await client.delete(f"{USERS}/{uuid4()}", headers=headers)

    assert (patched.status_code, deleted.status_code) == (404, 404)


async def test_organizer_is_forbidden(client: httpx.AsyncClient, make_user: UserFactory) -> None:
    headers = await bearer(client, await make_user())

    listed = await client.get(USERS, headers=headers)
    patched = await client.patch(f"{USERS}/{uuid4()}", json={"status": "blocked"}, headers=headers)
    deleted = await client.delete(f"{USERS}/{uuid4()}", headers=headers)

    assert {listed.status_code, patched.status_code, deleted.status_code} == {403}
    assert listed.json()["code"] == "forbidden"


async def test_admin_api_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.get(USERS)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("params", "loc"),
    [
        pytest.param({"status": "deleted"}, ["query", "status"], id="unknown-status"),
        pytest.param({"cursor": "not-a-cursor"}, ["query", "cursor"], id="foreign-cursor"),
        pytest.param({"limit": 101}, ["query", "limit"], id="limit"),
    ],
)
async def test_invalid_list_query_is_422(
    client: httpx.AsyncClient, admin: User, params: dict[str, str | int], loc: list[str]
) -> None:
    response = await client.get(USERS, params=params, headers=await bearer(client, admin))

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == loc


async def test_invalid_update_is_422(client: httpx.AsyncClient, make_user: UserFactory, admin: User) -> None:
    user = await make_user()

    response = await client.patch(f"{USERS}/{user.id}", json={"role": "owner"}, headers=await bearer(client, admin))

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "role"]
