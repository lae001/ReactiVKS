"""Учетная запись и правила ее полей."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from auth_service.domain.errors import InvalidDisplayName, InvalidEmail, LastAdmin, UserBlocked
from auth_service.domain.identifiers import UserId

__all__ = [
    "MAX_DISPLAY_NAME_LENGTH",
    "MAX_EMAIL_LENGTH",
    "InvalidCursor",
    "Role",
    "User",
    "UserCursor",
    "UserQuery",
    "UserStatus",
    "ensure_admin_remains",
    "normalize_display_name",
    "normalize_email",
]

MAX_EMAIL_LENGTH = 254
MAX_DISPLAY_NAME_LENGTH = 100

# Строже ограничения БД (users_email_ck): в домене после @ нужна точка. Полная проверка RFC 5322 здесь ни к чему –
# адрес подтверждается тем, что человек им пользуется, а не регулярным выражением.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Role(StrEnum):
    ORGANIZER = "organizer"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class User:
    """Организатор или администратор. Хеш пароля – часть сущности, но наружу (API, журналы) не выходит."""

    id: UserId
    email: str
    password_hash: str
    display_name: str
    role: Role
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None = None

    @property
    def is_blocked(self) -> bool:
        return self.status is UserStatus.BLOCKED

    def ensure_can_sign_in(self) -> None:
        """Войти может только активная учетная запись. Вызывается после проверки пароля."""
        if self.is_blocked:
            raise UserBlocked()

    @property
    def is_active_admin(self) -> bool:
        return self.role is Role.ADMIN and self.status is UserStatus.ACTIVE

    def renamed(self, display_name: str) -> User:
        """Та же учетная запись с новым отображаемым именем (уже нормализованным)."""
        return replace(self, display_name=display_name)

    def administered(self, *, status: UserStatus | None = None, role: Role | None = None) -> User:
        """Учетная запись после решения администратора; ``None`` – оставить как есть. Без изменений – тот же объект."""
        changed = replace(self, status=status or self.status, role=role or self.role)
        return self if changed == self else changed


def ensure_admin_remains(*, actor_id: UserId, before: User, after: User | None, active_admins: int) -> None:
    """Проверить изменение учетной записи администратором (``after = None`` – удаление).

    Себя администратор не блокирует, не понижает и не удаляет; последнего активного администратора не теряет никто.
    ``active_admins`` – число активных администраторов до изменения, посчитанное под блокировкой.
    """
    if after is before:
        return
    if before.id == actor_id:
        raise LastAdmin("Administrators cannot block, demote or delete themselves")
    loses_admin = before.is_active_admin and (after is None or not after.is_active_admin)
    if loses_admin and active_admins <= 1:
        raise LastAdmin()


@dataclass(frozen=True, slots=True)
class UserQuery:
    """Фильтры списка пользователей: подстрока e-mail или имени и статус."""

    text: str | None = None
    status: UserStatus | None = None


class InvalidCursor(ValueError):
    """Курсор не выдан этим сервисом или поврежден."""


@dataclass(frozen=True, slots=True)
class UserCursor:
    """Позиция в списке пользователей: ``created_at`` и ``id`` последней выданной записи (курсорная пагинация)."""

    created_at: datetime
    user_id: UUID

    def encode(self) -> str:
        payload = json.dumps({"k": self.created_at.isoformat(), "id": str(self.user_id)}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, value: str) -> UserCursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
            created_at = datetime.fromisoformat(payload["k"])
            user_id = UUID(payload["id"])
        except (binascii.Error, ValueError, TypeError, KeyError) as error:
            raise InvalidCursor("cursor is not valid") from error
        if created_at.tzinfo is None:
            raise InvalidCursor("cursor is not valid")
        return cls(created_at=created_at, user_id=user_id)


def normalize_email(raw: str) -> str:
    """Адрес без пробелов по краям и в нижнем регистре – в таком виде он хранится и сравнивается."""
    email = raw.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(email):
        raise InvalidEmail("Email address is not valid", field="email")
    return email


def normalize_display_name(raw: str) -> str:
    """Имя без пробелов по краям, от 1 до 100 символов."""
    name = raw.strip()
    if not name or len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise InvalidDisplayName(
            f"Display name must be 1 to {MAX_DISPLAY_NAME_LENGTH} characters long",
            field="display_name",
        )
    return name
