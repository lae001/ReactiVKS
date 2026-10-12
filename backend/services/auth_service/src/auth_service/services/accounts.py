"""Создание учетных записей: регистрация организатора (API) и первый администратор (CLI).

Обе – один и тот же путь: нормализация, политика пароля, хеш вне транзакции, вставка. Различаются роль и то, что
регистрацию можно выключить, а создание администратора из консоли – нет.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import RegistrationClosed
from auth_service.domain.identifiers import UserId
from auth_service.domain.passwords import PasswordHasher, check_password_policy
from auth_service.domain.users import Role, User, UserStatus, normalize_display_name, normalize_email
from auth_service.repositories.users import UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.ids import new_id
from vks_common.logging import get_logger

__all__ = ["CreateAdmin", "RegisterOrganizer"]

_logger = get_logger(__name__)


class _AccountCreator:
    """Общая часть обоих сценариев."""

    def __init__(self, *, session: AsyncSession, hasher: PasswordHasher, clock: Clock) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._hasher = hasher
        self._clock = clock

    async def create(self, *, email: str, password: str, display_name: str, role: Role) -> User:
        normalized_email = normalize_email(email)
        normalized_name = normalize_display_name(display_name)
        check_password_policy(password)

        # Argon2 занимает CPU на десятки миллисекунд: в потоке и до открытия транзакции, чтобы не держать соединение.
        password_hash = await asyncio.to_thread(self._hasher.hash, password)
        user = User(
            id=UserId(new_id()),
            email=normalized_email,
            password_hash=password_hash,
            display_name=normalized_name,
            role=role,
            status=UserStatus.ACTIVE,
            created_at=self._clock.now(),
        )
        # Занятый адрес обнаруживает ограничение БД: предварительную проверку одновременные регистрации прошли бы обе.
        async with transaction(self._session):
            await self._users.add(user)
        # В журнал – только идентификатор, не адрес и не имя.
        _logger.info("user created", user_id=str(user.id), role=role.value)
        return user


class RegisterOrganizer:
    """Открытая регистрация организатора (UC-1)."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        hasher: PasswordHasher,
        clock: Clock,
        registration_enabled: bool,
    ) -> None:
        self._creator = _AccountCreator(session=session, hasher=hasher, clock=clock)
        self._registration_enabled = registration_enabled

    async def execute(self, *, email: str, password: str, display_name: str) -> User:
        if not self._registration_enabled:
            raise RegistrationClosed()
        return await self._creator.create(
            email=email, password=password, display_name=display_name, role=Role.ORGANIZER
        )


class CreateAdmin:
    """Первый администратор – из консоли сервера (``vks-auth create-admin``), даже при выключенной регистрации."""

    def __init__(self, *, session: AsyncSession, hasher: PasswordHasher, clock: Clock) -> None:
        self._creator = _AccountCreator(session=session, hasher=hasher, clock=clock)

    async def execute(self, *, email: str, password: str, display_name: str) -> User:
        return await self._creator.create(email=email, password=password, display_name=display_name, role=Role.ADMIN)
