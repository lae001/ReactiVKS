"""Проверка access-токенов JWT RS256 в каждом сервисе (ADR-005)."""

from vks_common.auth.claims import ROLE_ADMIN, ROLE_ORGANIZER, USER_ROLES, AuthenticatedUser
from vks_common.auth.dependencies import (
    CurrentAdmin,
    CurrentUser,
    require_admin,
    require_user,
    use_authentication,
)
from vks_common.auth.jwks import JwksKeys
from vks_common.auth.keys import StaticKeys, UnknownSigningKey, VerificationKeys, key_from_jwk, key_from_pem
from vks_common.auth.verifier import ALGORITHM, InvalidToken, TokenVerifier

__all__ = [
    "ALGORITHM",
    "ROLE_ADMIN",
    "ROLE_ORGANIZER",
    "USER_ROLES",
    "AuthenticatedUser",
    "CurrentAdmin",
    "CurrentUser",
    "InvalidToken",
    "JwksKeys",
    "StaticKeys",
    "TokenVerifier",
    "UnknownSigningKey",
    "VerificationKeys",
    "key_from_jwk",
    "key_from_pem",
    "require_admin",
    "require_user",
    "use_authentication",
]
