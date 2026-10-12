"""Учетные записи: ``auth.users``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import EmailTaken
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import Role, User, UserStatus
from auth_service.models import UserRow
from vks_common.db import is_unique_violation

__all__ = ["UserRepository"]

# Уникальность e-mail держит ограничение БД (citext): две одновременные регистрации одного адреса проходят любую
# проверку в коде, и решает, кто из них опоздал, именно оно.
_EMAIL_UNIQUE_CONSTRAINT = "users_email_uk"


class UserRepository:
    """Чтение и запись учетных записей в транзакции вызывающего сценария; сам не коммитит."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        """Добавить учетную запись. Занятый адрес – :class:`EmailTaken`."""
        self._session.add(
            UserRow(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                display_name=user.display_name,
                role=user.role.value,
                status=user.status.value,
                created_at=user.created_at,
                updated_at=user.created_at,
                last_login_at=user.last_login_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if is_unique_violation(error, constraint=_EMAIL_UNIQUE_CONSTRAINT):
                raise EmailTaken("This email is already registered") from error
            raise

    async def get_by_id(self, user_id: UserId) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return _to_domain(row) if row is not None else None

    async def get_by_email(self, email: str) -> User | None:
        """Поиск по нормализованному адресу; ``citext`` сравнивает без учета регистра в любом случае."""
        row = (await self._session.execute(select(UserRow).where(UserRow.email == email))).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def rename(self, user_id: UserId, display_name: str, *, now: datetime) -> User | None:
        """Сменить отображаемое имя; ``None`` – учетной записи больше нет."""
        statement = (
            update(UserRow)
            .where(UserRow.id == user_id)
            .values(display_name=display_name, updated_at=now)
            .returning(UserRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def record_login(self, user_id: UserId, *, at: datetime) -> None:
        await self._session.execute(update(UserRow).where(UserRow.id == user_id).values(last_login_at=at))


def _to_domain(row: UserRow) -> User:
    return User(
        id=UserId(row.id),
        email=row.email,
        password_hash=row.password_hash,
        display_name=row.display_name,
        role=Role(row.role),
        status=UserStatus(row.status),
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )
