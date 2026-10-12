"""Argon2id за портом :class:`~auth_service.domain.passwords.PasswordHasher`."""

from __future__ import annotations

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

__all__ = ["Argon2Hasher"]

# Проверяется вместо пароля, когда пользователя нет, – чтобы ответ стоил столько же. Не хранится и не сравнивается
# с вводом пользователя.
_DUMMY_PASSWORD = "argon2-timing-equaliser"  # noqa: S105 - не учетные данные


class Argon2Hasher:
    """Хеширование паролей Argon2id (``argon2-cffi``)."""

    def __init__(self, *, time_cost: int, memory_kib: int, parallelism: int) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_kib,
            parallelism=parallelism,
            type=Type.ID,
        )
        # Строится один раз: смысл фиктивной проверки – стоить как настоящая, а хеширование на каждый вызов
        # удвоило бы ее цену.
        self._dummy_hash = self._hasher.hash(_DUMMY_PASSWORD)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        """Поврежденный хеш – несовпадение, а не падение: испорченная строка не должна превращать вход в 500."""
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verify_dummy(self) -> None:
        self._hasher.verify(self._dummy_hash, _DUMMY_PASSWORD)
