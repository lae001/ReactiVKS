from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from auth_service.main import create_application
from auth_service.settings import AuthSettings
from vks_common.auth import JwksKeys, TokenVerifier

pytestmark = pytest.mark.integration


async def test_service_is_alive(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.json()["service"] == "auth-service"


async def test_config_reports_flags(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/config")

    assert response.json() == {"registration_enabled": True, "password_reset_enabled": False}


async def test_config_reports_closed_registration(
    make_settings: Callable[..., AuthSettings],
) -> None:
    app = create_application(make_settings(auth_registration_enabled=False))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver") as http:
        response = await http.get("/api/v1/auth/config")

    assert response.json()["registration_enabled"] is False


async def test_jwks_publishes_signing_key_with_cache_header(client: httpx.AsyncClient, app: FastAPI) -> None:
    response = await client.get("/api/v1/auth/.well-known/jwks.json")

    (jwk,) = response.json()["keys"]
    assert jwk["kid"] == app.state.token_signer.kid
    assert {jwk["kty"], jwk["use"], jwk["alg"], jwk["e"]} == {"RSA", "sig", "RS256", "AQAB"}
    assert response.headers["cache-control"] == "public, max-age=300"


async def test_other_services_verify_tokens_through_jwks(client: httpx.AsyncClient, app: FastAPI) -> None:
    # Так access-токен проверяет meeting-service: ключ – из JWKS по HTTP, правила – из vks_common.
    now = int(datetime.now(UTC).timestamp())
    user_id = uuid4()
    token = app.state.token_signer.sign(
        {
            "iss": "vks-auth",
            "aud": "vks",
            "sub": str(user_id),
            "role": "organizer",
            "name": "Иван",
            "iat": now,
            "exp": now + 900,
            "jti": str(uuid4()),
        }
    )
    keys = JwksKeys("https://testserver/api/v1/auth/.well-known/jwks.json", http_client=client)

    user = await TokenVerifier(keys=keys, issuer="vks-auth", audience="vks").verify(token)

    assert user.user_id == user_id
