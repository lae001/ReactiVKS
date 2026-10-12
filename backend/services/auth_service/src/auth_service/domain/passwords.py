"""Политика паролей и порт хеширования.

Политика одна для регистрации, смены и восстановления пароля (rest-api.md). Значение пароля не попадает ни в
сообщение, ни в журнал, ни в исключение.
"""

from __future__ import annotations

from typing import Protocol

from auth_service.domain.errors import WeakPassword

__all__ = ["MAX_PASSWORD_LENGTH", "MIN_PASSWORD_LENGTH", "PasswordHasher", "check_password_policy"]

MIN_PASSWORD_LENGTH = 8
# Ограничение стоимости, а не безопасности: Argon2 хеширует все, что дали, и мегабайт пароля – способ занять CPU.
MAX_PASSWORD_LENGTH = 128


class PasswordHasher(Protocol):
    """Что сценариям нужно от хеша пароля."""

    def hash(self, password: str) -> str:
        """Самоописывающий хеш: алгоритм, параметры, соль, результат."""
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        """Получен ли этот хеш из этого пароля."""
        ...

    def verify_dummy(self) -> None:
        """Потратить столько же, сколько настоящая проверка, – когда проверять не с чем.

        Без этого «нет такого пользователя» отвечало бы за микросекунды, а «неверный пароль» – за время Argon2,
        и по разнице перебирались бы адреса учетных записей.
        """
        ...


def check_password_policy(password: str, *, field: str = "password") -> None:
    """Принять пароль или сказать, какое правило он нарушил.

    Силу дает длина; требование буквы и цифры отсекает длинные, но тривиальные пароли – ``aaaaaaaa``, ``12345678``.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long", field=field)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long", field=field)
    if password != password.strip():
        raise WeakPassword("Password must not start or end with whitespace", field=field)
    if not any(character.isalpha() for character in password):
        raise WeakPassword("Password must contain at least one letter", field=field)
    if not any(character.isdigit() for character in password):
        raise WeakPassword("Password must contain at least one digit", field=field)
