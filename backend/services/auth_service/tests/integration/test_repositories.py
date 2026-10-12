from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import EmailTaken
from auth_service.domain.identifiers import RefreshTokenId, SessionFamilyId, UserId
from auth_service.domain.sessions import RefreshToken, hash_refresh_token
from auth_service.domain.users import Role, User, UserStatus
from auth_service.repositories.refresh_tokens import RefreshTokenRepository
from auth_service.repositories.users import UserRepository
from vks_common.db import transaction
from vks_common.ids import new_id, new_token

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def make_user(**overrides: object) -> User:
    fields: dict[str, object] = {
        "id": UserId(new_id()),
        "email": f"user-{new_token(6).lower()}@example.ru",
        "password_hash": "$argon2id$stub",
        "display_name": "Иван Петров",
        "role": Role.ORGANIZER,
        "status": UserStatus.ACTIVE,
        "created_at": NOW,
    }
    fields.update(overrides)
    return User(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


def make_token(user: User, *, family_id: SessionFamilyId | None = None) -> RefreshToken:
    return RefreshToken(
        id=RefreshTokenId(new_id()),
        user_id=user.id,
        family_id=family_id or SessionFamilyId(new_id()),
        token_hash=hash_refresh_token(new_token()),
        expires_at=NOW + timedelta(days=30),
    )


async def test_added_user_is_found_by_id_and_email(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = make_user(email="anna@example.ru")

    async with transaction(session):
        await users.add(user)

    assert await users.get_by_id(user.id) == user
    assert await users.get_by_email("anna@example.ru") == user
    assert await users.get_by_email("ANNA@example.ru") == user


async def test_second_account_with_same_email_is_email_taken(session: AsyncSession) -> None:
    users = UserRepository(session)
    async with transaction(session):
        await users.add(make_user(email="taken@example.ru"))

    with pytest.raises(EmailTaken):
        async with transaction(session):
            await users.add(make_user(email="Taken@Example.ru"))


async def test_unknown_user_is_none(session: AsyncSession) -> None:
    users = UserRepository(session)

    assert await users.get_by_id(UserId(new_id())) is None
    assert await users.get_by_email("nobody@example.ru") is None


async def test_rename_returns_updated_user(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = make_user()
    async with transaction(session):
        await users.add(user)

    async with transaction(session):
        renamed = await users.rename(user.id, "Анна", now=NOW + timedelta(hours=1))

    assert renamed == user.renamed("Анна")


async def test_rename_of_missing_user_is_none(session: AsyncSession) -> None:
    async with transaction(session):
        assert await UserRepository(session).rename(UserId(new_id()), "Анна", now=NOW) is None


async def test_login_moment_is_recorded(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = make_user()
    async with transaction(session):
        await users.add(user)

    async with transaction(session):
        await users.record_login(user.id, at=NOW + timedelta(minutes=5))

    found = await users.get_by_id(user.id)
    assert found is not None
    assert found.last_login_at == NOW + timedelta(minutes=5)


async def test_token_is_found_by_hash_with_and_without_lock(session: AsyncSession) -> None:
    user = make_user()
    token = make_token(user)
    tokens = RefreshTokenRepository(session)
    async with transaction(session):
        await UserRepository(session).add(user)
        await tokens.add(token, user_agent="Firefox", created_at=NOW)

    async with transaction(session):
        locked = await tokens.lock_by_hash(token.token_hash)

    assert locked == token
    assert await tokens.get_by_hash(token.token_hash) == token
    assert await tokens.get_by_hash(hash_refresh_token("unknown")) is None


async def test_rotation_is_saved(session: AsyncSession) -> None:
    user = make_user()
    token = make_token(user)
    successor = make_token(user, family_id=token.family_id)
    tokens = RefreshTokenRepository(session)
    async with transaction(session):
        await UserRepository(session).add(user)
        await tokens.add(token, user_agent=None, created_at=NOW)

    async with transaction(session):
        await tokens.add(successor, user_agent=None, created_at=NOW)
        await tokens.save_rotation(token.rotated(successor=successor.id, now=NOW))

    stored = await tokens.get_by_hash(token.token_hash)
    assert stored is not None
    assert stored.is_spent
    assert stored.replaced_by == successor.id


async def test_family_revocation_touches_only_live_tokens_of_that_family(session: AsyncSession) -> None:
    user = make_user()
    family = SessionFamilyId(new_id())
    spent = make_token(user, family_id=family).rotated(successor=RefreshTokenId(new_id()), now=NOW)
    live = make_token(user, family_id=family)
    other_device = make_token(user)
    tokens = RefreshTokenRepository(session)
    async with transaction(session):
        await UserRepository(session).add(user)
        for token in (spent, live, other_device):
            await tokens.add(token, user_agent=None, created_at=NOW)

    async with transaction(session):
        revoked = await tokens.revoke_family(family, at=NOW + timedelta(minutes=1))

    assert revoked == 1
    stored_other = await tokens.get_by_hash(other_device.token_hash)
    assert stored_other is not None
    assert not stored_other.is_spent
