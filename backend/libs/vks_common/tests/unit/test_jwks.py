import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from vks_common.auth import JwksKeys, UnknownSigningKey

JWKS_URL = "http://auth-service:8001/api/v1/auth/.well-known/jwks.json"


def public_jwk(kid: str) -> dict[str, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(key, as_dict=True)
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


class FakeAuthService:
    """Отвечает на запрос JWKS текущим набором ключей и считает запросы."""

    def __init__(self, *kids: str) -> None:
        self.keys = [public_jwk(kid) for kid in kids]
        self.requests = 0
        self.is_down = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.is_down:
            return httpx.Response(503)
        return httpx.Response(200, json={"keys": self.keys})


class ManualClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def jwks_keys(auth: FakeAuthService, clock: ManualClock) -> JwksKeys:
    client = httpx.AsyncClient(transport=httpx.MockTransport(auth.handle))
    return JwksKeys(
        JWKS_URL, http_client=client, cache_ttl_seconds=3600, refresh_min_interval_seconds=10, monotonic=clock
    )


async def test_keys_are_fetched_once_and_cached() -> None:
    auth, clock = FakeAuthService("k1"), ManualClock()
    keys = jwks_keys(auth, clock)

    await keys.key_for("k1")
    await keys.key_for("k1")

    assert auth.requests == 1


async def test_unknown_kid_triggers_refresh_after_rotation() -> None:
    auth, clock = FakeAuthService("k1"), ManualClock()
    keys = jwks_keys(auth, clock)
    await keys.key_for("k1")
    auth.keys.append(public_jwk("k2"))
    clock.now += 11

    await keys.key_for("k2")

    assert auth.requests == 2


async def test_unknown_kids_do_not_flood_auth_service() -> None:
    auth, clock = FakeAuthService("k1"), ManualClock()
    keys = jwks_keys(auth, clock)
    await keys.key_for("k1")

    for _ in range(5):
        with pytest.raises(UnknownSigningKey):
            await keys.key_for("forged")

    assert auth.requests == 1


async def test_known_keys_survive_auth_service_outage() -> None:
    auth, clock = FakeAuthService("k1"), ManualClock()
    keys = jwks_keys(auth, clock)
    first = await keys.key_for("k1")
    auth.is_down = True
    clock.now += 3601

    assert await keys.key_for("k1") is first
    assert auth.requests == 2


async def test_unavailable_auth_service_is_retried_with_rate_limit() -> None:
    auth, clock = FakeAuthService("k1"), ManualClock()
    auth.is_down = True
    keys = jwks_keys(auth, clock)

    for _ in range(3):
        with pytest.raises(UnknownSigningKey):
            await keys.key_for("k1")
    clock.now += 11
    auth.is_down = False
    await keys.key_for("k1")

    assert auth.requests == 2
