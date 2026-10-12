"""Учетная запись и правила ее полей."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from auth_service.domain.errors import InvalidDisplayName, InvalidEmail
from auth_service.domain.identifiers import UserId

__all__ = [
    "MAX_DISPLAY_NAME_LENGTH",
    "MAX_EMAIL_LENGTH",
    "Role",
    "User",
    "UserStatus",
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

    def renamed(self, display_name: str) -> User:
        """Та же учетная запись с новым отображаемым именем (уже нормализованным)."""
        return replace(self, display_name=display_name)


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
