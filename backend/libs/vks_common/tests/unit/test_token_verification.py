from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI

from vks_common.auth import (
    ROLE_ADMIN,
    AuthenticatedUser,
    CurrentAdmin,
    CurrentUser,
    InvalidToken,
    use_authentication,
)
from vks_common.problem_details import install_error_handlers
from vks_common.testing import TokenFactory, app_client


@pytest.fixture(scope="module")
def tokens() -> TokenFactory:
    return TokenFactory()


async def test_valid_token_yields_user(tokens: TokenFactory) -> None:
    user_id = uuid4()

    user = await tokens.verifier().verify(tokens.issue(user_id=user_id, name="Анна"))

    assert user.user_id == user_id
    assert user.role == "organizer"
    assert user.name == "Анна"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"iss": "someone-else"}, id="wrong-issuer"),
        pytest.param({"aud": "other-audience"}, id="wrong-audience"),
        pytest.param({"jti": None}, id="no-jti"),
        pytest.param({"role": "guest"}, id="unknown-role"),
        pytest.param({"sub": "not-a-uuid"}, id="malformed-subject"),
    ],
)
async def test_token_with_wrong_claims_is_rejected(tokens: TokenFactory, overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidToken):
        await tokens.verifier().verify(tokens.issue(claims=overrides))


async def test_expired_token_is_rejected(tokens: TokenFactory) -> None:
    token = tokens.issue(issued_at=datetime.now(UTC) - timedelta(hours=1))

    with pytest.raises(InvalidToken):
        await tokens.verifier().verify(token)


async def test_token_signed_by_another_key_is_rejected(tokens: TokenFactory) -> None:
    forged = TokenFactory(kid=tokens.kid).issue()

    with pytest.raises(InvalidToken):
        await tokens.verifier().verify(forged)


async def test_token_with_unknown_kid_is_rejected(tokens: TokenFactory) -> None:
    with pytest.raises(InvalidToken):
        await tokens.verifier().verify(TokenFactory(kid="unknown").issue())


async def test_symmetric_algorithm_is_not_accepted(tokens: TokenFactory) -> None:
    # Классическая подмена: HS256 с открытым ключом в роли общего секрета.
    claims = jwt.decode(tokens.issue(), options={"verify_signature": False})
    secret = "public-key-used-as-an-hmac-shared-secret"
    forged = jwt.encode(claims, secret, algorithm="HS256", headers={"kid": tokens.kid})

    with pytest.raises(InvalidToken):
        await tokens.verifier().verify(forged)


def build_app(tokens: TokenFactory) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    use_authentication(app, tokens.verifier())

    @app.get("/me")
    async def me(user: CurrentUser) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    @app.get("/admin")
    async def admin(user: CurrentAdmin) -> dict[str, str]:
        return {"role": user.role}

    return app


async def test_endpoint_without_token_answers_401(tokens: TokenFactory) -> None:
    async with app_client(build_app(tokens)) as http:
        response = await http.get("/me")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_endpoint_with_invalid_token_answers_401(tokens: TokenFactory) -> None:
    async with app_client(build_app(tokens)) as http:
        response = await http.get("/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401


async def test_endpoint_with_valid_token_sees_user(tokens: TokenFactory) -> None:
    user_id = uuid4()

    async with app_client(build_app(tokens)) as http:
        response = await http.get("/me", headers={"Authorization": f"Bearer {tokens.issue(user_id=user_id)}"})

    assert response.json() == {"user_id": str(user_id)}


async def test_admin_endpoint_refuses_organizer_with_403(tokens: TokenFactory) -> None:
    async with app_client(build_app(tokens)) as http:
        response = await http.get("/admin", headers={"Authorization": f"Bearer {tokens.issue()}"})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_admin_endpoint_admits_admin(tokens: TokenFactory) -> None:
    async with app_client(build_app(tokens)) as http:
        response = await http.get("/admin", headers={"Authorization": f"Bearer {tokens.issue(role=ROLE_ADMIN)}"})

    assert response.json() == {"role": "admin"}


def test_authenticated_user_knows_admin_role() -> None:
    user = AuthenticatedUser(user_id=uuid4(), role=ROLE_ADMIN, name="A", token_id="t", expires_at=datetime.now(UTC))

    assert user.is_admin
