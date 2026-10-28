"""Учетные записи: ``auth.users``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Uuid, delete, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import EmailTaken
from auth_service.domain.identifiers import UserId
from auth_service.domain.users import Role, User, UserCursor, UserQuery, UserStatus
from auth_service.models import UserRow
from vks_common.db import is_unique_violation

__all__ = ["UserPage", "UserRepository"]

# Уникальность e-mail держит ограничение БД (citext): две одновременные регистрации одного адреса проходят любую
# проверку в коде, и решает, кто из них опоздал, именно оно.
_EMAIL_UNIQUE_CONSTRAINT = "users_email_uk"


@dataclass(frozen=True, slots=True)
class UserPage:
    """Страница списка и курсор следующей (``None`` – страница последняя)."""

    items: list[User]
    next_cursor: UserCursor | None


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

    async def change_password_hash(self, user_id: UserId, password_hash: str, *, now: datetime) -> bool:
        """Заменить хеш пароля; ``False`` – учетной записи больше нет."""
        result = await self._session.execute(
            update(UserRow)
            .where(UserRow.id == user_id)
            .values(password_hash=password_hash, updated_at=now)
            .returning(UserRow.id)
        )
        return result.scalar_one_or_none() is not None

    async def record_login(self, user_id: UserId, *, at: datetime) -> None:
        await self._session.execute(update(UserRow).where(UserRow.id == user_id).values(last_login_at=at))

    async def lock(self, user_id: UserId) -> User | None:
        """Учетная запись под ``FOR UPDATE`` до конца транзакции."""
        statement = select(UserRow).where(UserRow.id == user_id).with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def lock_active_admins(self) -> int:
        """Число активных администраторов; их строки блокируются до конца транзакции.

        Без блокировки два администратора, одновременно понижающие друг друга, оба увидели бы «есть еще один» и
        оставили бы Систему без администраторов. Порядок по ``id`` – одинаковый во всех транзакциях, без взаимной
        блокировки.
        """
        statement = (
            select(UserRow.id)
            .where(UserRow.role == Role.ADMIN.value, UserRow.status == UserStatus.ACTIVE.value)
            .order_by(UserRow.id)
            .with_for_update()
        )
        return len((await self._session.execute(statement)).all())

    async def save_administration(self, user: User, *, now: datetime) -> None:
        """Записать статус и роль."""
        await self._session.execute(
            update(UserRow)
            .where(UserRow.id == user.id)
            .values(status=user.status.value, role=user.role.value, updated_at=now)
        )

    async def delete(self, user_id: UserId) -> None:
        """Удалить учетную запись; refresh-токены удаляются каскадом (``ON DELETE CASCADE``)."""
        await self._session.execute(delete(UserRow).where(UserRow.id == user_id))

    async def list_page(self, query: UserQuery, *, limit: int, after: UserCursor | None) -> UserPage:
        """Пользователи, новые сверху. Курсор – ``created_at`` и ``id`` последней выданной записи."""
        statement = (
            select(UserRow)
            .where(*_filters(query))
            .order_by(UserRow.created_at.desc(), UserRow.id.desc())
            # Лишняя строка показывает, есть ли следующая страница, без отдельного count.
            .limit(limit + 1)
        )
        if after is not None:
            position = tuple_(literal(after.created_at, TIMESTAMP(timezone=True)), literal(after.user_id, Uuid()))
            statement = statement.where(tuple_(UserRow.created_at, UserRow.id) < position)
        rows = list((await self._session.execute(statement)).scalars())
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = UserCursor(created_at=last.created_at, user_id=last.id)
        return UserPage(items=[_to_domain(row) for row in rows[:limit]], next_cursor=next_cursor)


def _filters(query: UserQuery) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if query.status is not None:
        filters.append(UserRow.status == query.status.value)
    if query.text:
        # Подстрока ищется буквально: % и _ из запроса администратора – символы, а не шаблоны LIKE.
        pattern = "%" + query.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(or_(UserRow.email.ilike(pattern, escape="\\"), UserRow.display_name.ilike(pattern, escape="\\")))
    return filters


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
