"""Профиль текущего пользователя: просмотр, смена имени, смена пароля."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import AccountGone, InvalidCredentials
from auth_service.domain.identifiers import UserId
from auth_service.domain.passwords import PasswordHasher, check_password_policy
from auth_service.domain.users import User, normalize_display_name
from auth_service.repositories.refresh_tokens import RefreshTokenRepository
from auth_service.repositories.users import UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.logging import get_logger

__all__ = ["ChangePassword", "GetProfile", "RenameUser"]

_logger = get_logger(__name__)


class GetProfile:
    """Учетная запись вызывающего по ``sub`` его access-токена."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def execute(self, *, user_id: UserId) -> User:
        async with transaction(self._session):
            user = await self._users.get_by_id(user_id)
        if user is None:
            raise AccountGone()
        return user


class RenameUser:
    """Смена отображаемого имени. Claim ``name`` в access-токене обновится при следующем обмене refresh-токена."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._clock = clock

    async def execute(self, *, user_id: UserId, display_name: str) -> User:
        name = normalize_display_name(display_name)
        async with transaction(self._session):
            user = await self._users.rename(user_id, name, now=self._clock.now())
        if user is None:
            raise AccountGone()
        return user


class ChangePassword:
    """Смена пароля по текущему паролю. Все сессии пользователя завершаются.

    Отзываются все refresh-токены, а не «все, кроме текущего»: cookie ``vks_refresh`` ограничена путем
    ``/api/v1/auth`` и на ``/users/me/password`` не приходит, так что текущую сессию сервер не знает. Выданный
    access-токен действует до истечения срока (до 15 минут); клиент входит заново с новым паролем.
    """

    def __init__(self, *, session: AsyncSession, hasher: PasswordHasher, clock: Clock) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._hasher = hasher
        self._clock = clock

    async def execute(self, *, user_id: UserId, current_password: str, new_password: str) -> None:
        async with transaction(self._session):
            user = await self._users.get_by_id(user_id)
        if user is None:
            raise AccountGone()
        # Argon2 занимает CPU на десятки миллисекунд: в потоке и вне транзакции, чтобы не держать соединение.
        if not await asyncio.to_thread(self._hasher.verify, current_password, user.password_hash):
            raise InvalidCredentials("Current password is not correct")
        check_password_policy(new_password, field="new_password")
        password_hash = await asyncio.to_thread(self._hasher.hash, new_password)

        now = self._clock.now()
        async with transaction(self._session):
            if not await self._users.change_password_hash(user_id, password_hash, now=now):
                raise AccountGone()
            sessions_ended = await self._tokens.revoke_all_for_user(user_id, at=now)
        _logger.info("password changed", user_id=str(user_id), sessions_ended=sessions_ended)
