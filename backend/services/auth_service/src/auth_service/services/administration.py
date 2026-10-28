"""Администрирование учетных записей (функция 6.11): список, блокировка, смена роли, удаление.

Блокировка и удаление публикуют ``user.blocked`` / ``user.deleted`` через outbox: meeting-service по ним не пускает
заблокированного организатора во встречи и удаляет встречи удаленного.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import UserNotFound
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import Role, User, UserCursor, UserQuery, UserStatus, ensure_admin_remains
from auth_service.repositories.outbox import EventOutbox
from auth_service.repositories.refresh_tokens import RefreshTokenRepository
from auth_service.repositories.users import UserPage, UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.logging import get_logger
from vks_contracts.user_events import UserBlocked, UserDeleted, UserUnblocked

__all__ = ["DeleteUser", "ListUsers", "UpdateUser"]

_logger = get_logger(__name__)


class ListUsers:
    """Учетные записи для администратора, новые сверху."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def execute(self, *, query: UserQuery, limit: int, after: UserCursor | None = None) -> UserPage:
        async with transaction(self._session):
            return await self._users.list_page(query, limit=limit, after=after)


class UpdateUser:
    """Блокировка, разблокировка и смена роли. Блокировка завершает все сессии пользователя.

    Выданный access-токен заблокированного действует до истечения срока (до 15 минут): auth-service его не
    отзывает, а meeting-service не пускает такого организатора во встречи по событию ``user.blocked``.
    """

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock

    async def execute(
        self,
        *,
        actor_id: UserId,
        user_id: UserId,
        status: UserStatus | None = None,
        role: Role | None = None,
    ) -> User:
        now = self._clock.now()
        async with transaction(self._session):
            active_admins = await self._users.lock_active_admins()
            user = await self._users.lock(user_id)
            if user is None:
                raise UserNotFound()
            updated = user.administered(status=status, role=role)
            ensure_admin_remains(actor_id=actor_id, before=user, after=updated, active_admins=active_admins)
            if updated is user:
                return user
            await self._users.save_administration(updated, now=now)
            if updated.status is not user.status:
                if updated.is_blocked:
                    sessions_ended = await self._tokens.revoke_all_for_user(user_id, at=now)
                    await self._events.add(UserBlocked(user_id=user_id), occurred_at=now)
                    _logger.info("user blocked", user_id=str(user_id), sessions_ended=sessions_ended)
                else:
                    await self._events.add(UserUnblocked(user_id=user_id), occurred_at=now)
                    _logger.info("user unblocked", user_id=str(user_id))
            if updated.role is not user.role:
                _logger.info("user role changed", user_id=str(user_id), role=updated.role.value)
        return updated


class DeleteUser:
    """Удаление учетной записи. Встречи и аналитику пользователя удаляют другие сервисы по ``user.deleted``."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock

    async def execute(self, *, actor_id: UserId, user_id: UserId) -> None:
        now = self._clock.now()
        async with transaction(self._session):
            active_admins = await self._users.lock_active_admins()
            user = await self._users.lock(user_id)
            if user is None:
                raise UserNotFound()
            ensure_admin_remains(actor_id=actor_id, before=user, after=None, active_admins=active_admins)
            await self._users.delete(user_id)
            await self._events.add(UserDeleted(user_id=user_id), occurred_at=now)
        _logger.info("user deleted", user_id=str(user_id))
