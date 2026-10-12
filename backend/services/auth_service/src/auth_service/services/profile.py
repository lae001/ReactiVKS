"""Профиль текущего пользователя."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import AccountGone
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import User, normalize_display_name
from auth_service.repositories.users import UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction

__all__ = ["GetProfile", "RenameUser"]


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
