import time
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.adapters.rsa_keys import InvalidSigningKey, RsaKeyRing, jwk_thumbprint
from vks_common.auth import StaticKeys, TokenVerifier


def private_pem(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


@pytest.fixture(scope="module")
def hasher() -> Argon2Hasher:
    return Argon2Hasher(time_cost=1, memory_kib=8, parallelism=1)


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_password_verifies_against_its_hash(hasher: Argon2Hasher) -> None:
    password_hash = hasher.hash("correct8")

    assert password_hash.startswith("$argon2id$")
    assert hasher.verify("correct8", password_hash)
    assert not hasher.verify("wrong-password1", password_hash)


def test_same_password_gets_different_salted_hashes(hasher: Argon2Hasher) -> None:
    assert hasher.hash("correct8") != hasher.hash("correct8")


def test_malformed_hash_is_a_mismatch_not_a_crash(hasher: Argon2Hasher) -> None:
    assert not hasher.verify("correct8", "not-a-hash")


def test_dummy_verification_does_not_raise(hasher: Argon2Hasher) -> None:
    hasher.verify_dummy()


def test_thumbprint_matches_rfc_7638_example() -> None:
    # Пример из RFC 7638, раздел 3.1.
    jwk = {
        "kty": "RSA",
        "n": (
            "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWK"
            "RXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMic"
            "AtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3"
            "XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw"
        ),
        "e": "AQAB",
        "alg": "RS256",
        "kid": "2011-04-29",
    }

    assert jwk_thumbprint(jwk) == "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs"


def test_same_key_always_gets_same_kid(rsa_key: rsa.RSAPrivateKey) -> None:
    assert RsaKeyRing(private_pem(rsa_key)).kid == RsaKeyRing(private_pem(rsa_key)).kid


async def test_signed_token_verifies_with_published_keys(rsa_key: rsa.RSAPrivateKey) -> None:
    ring = RsaKeyRing(private_pem(rsa_key))
    user_id = uuid4()
    claims: dict[str, object] = {
        "iss": "vks-auth",
        "aud": "vks",
        "sub": str(user_id),
        "role": "organizer",
        "name": "Иван",
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
        "jti": str(uuid4()),
    }
    verifier = TokenVerifier(keys=StaticKeys(ring.verification_keys()), issuer="vks-auth", audience="vks")

    user = await verifier.verify(ring.sign(claims))

    assert user.user_id == user_id


def test_jwks_lists_current_key_for_signatures(rsa_key: rsa.RSAPrivateKey) -> None:
    ring = RsaKeyRing(private_pem(rsa_key))

    (jwk,) = ring.published_keys()

    assert jwk["kid"] == ring.kid
    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    assert jwk["e"] == "AQAB"


def test_previous_key_is_published_during_rotation(rsa_key: rsa.RSAPrivateKey) -> None:
    previous = RsaKeyRing(private_pem(rsa_key))
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    ring = RsaKeyRing(private_pem(new_key), previous_public_key_pem=public_pem(rsa_key))

    assert {jwk["kid"] for jwk in ring.published_keys()} == {ring.kid, previous.kid}
    assert set(ring.verification_keys()) == {ring.kid, previous.kid}


@pytest.mark.parametrize(
    "pem",
    [
        pytest.param("not a pem", id="garbage"),
        pytest.param(private_pem(ec.generate_private_key(ec.SECP256R1())), id="not-rsa"),
        pytest.param(
            private_pem(rsa.generate_private_key(public_exponent=65537, key_size=1024)),  # noqa: S505 - проверяется отказ
            id="too-short",
        ),
    ],
)
def test_unusable_signing_key_is_refused_at_startup(pem: str) -> None:
    with pytest.raises(InvalidSigningKey):
        RsaKeyRing(pem)
