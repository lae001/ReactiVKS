"""Порт доставки ссылки восстановления и ошибка одноразового токена."""

from typing import Protocol

from vks_common.errors import AppError


class ResetMailer(Protocol):
    async def send(self, email: str, token: str) -> None: ...


class ResetDeliveryError(Exception):
    """Почтовый транспорт недоступен; запрос не раскрывает существование адреса."""


class InvalidResetToken(AppError):
    code = "invalid_reset_token"
    status = 400
    title = "Reset token is invalid or expired"
