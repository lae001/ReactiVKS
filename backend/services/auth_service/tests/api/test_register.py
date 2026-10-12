from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_service.main import create_application
from auth_service.settings import AuthSettings
from vks_common.db import get_session
from vks_common.testing import app_client

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"


def registration(**overrides: object) -> dict[str, object]:
    return {"email": "ivan@example.ru", "password": "correct-horse-7", "display_name": "Иван Петров"} | overrides


async def test_registration_creates_active_organizer(client: httpx.AsyncClient) -> None:
    response = await client.post(REGISTER, json=registration(email="  Ivan@Example.RU "))

    body = response.json()
    assert response.status_code == 201
    assert body["email"] == "ivan@example.ru"
    assert body["display_name"] == "Иван Петров"
    assert body["role"] == "organizer"
    assert set(body) == {"id", "email", "display_name", "role"}
    assert "set-cookie" not in response.headers


async def test_password_is_stored_as_argon2id_hash(client: httpx.AsyncClient, session: AsyncSession) -> None:
    response = await client.post(REGISTER, json=registration())

    stored = await session.execute(
        text("SELECT password_hash, status FROM auth.users WHERE id = :id"), {"id": response.json()["id"]}
    )
    password_hash, status = stored.one()
    assert password_hash.startswith("$argon2id$")
    assert "correct-horse-7" not in password_hash
    assert status == "active"


async def test_taken_email_is_409_regardless_of_case(client: httpx.AsyncClient) -> None:
    await client.post(REGISTER, json=registration(email="anna@example.ru"))

    response = await client.post(REGISTER, json=registration(email="ANNA@example.ru"))

    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        pytest.param({"password": "onlyletters"}, "password", id="password-without-digit"),
        pytest.param({"password": "1234567"}, "password", id="password-too-short"),
        pytest.param({"email": "not-an-email"}, "email", id="malformed-email"),
        pytest.param({"display_name": "   "}, "display_name", id="blank-name"),
        pytest.param({"display_name": "x" * 101}, "display_name", id="long-name"),
    ],
)
async def test_invalid_input_is_422_pointing_to_field(
    client: httpx.AsyncClient, overrides: dict[str, object], field: str
) -> None:
    response = await client.post(REGISTER, json=registration(**overrides))

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert [error["loc"] for error in body["errors"]] == [["body", field]]


async def test_missing_field_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(REGISTER, json={"email": "ivan@example.ru", "password": "correct-horse-7"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "display_name"]


async def test_closed_registration_is_404(
    make_settings: Callable[..., AuthSettings],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_application(make_settings(auth_registration_enabled=False))

    async def isolated_session() -> object:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session

    async with app_client(app, base_url="https://testserver") as http:
        response = await http.post(REGISTER, json=registration())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
