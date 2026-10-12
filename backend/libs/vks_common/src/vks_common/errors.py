"""Базовые классы ожидаемых ошибок.

Домен и сценарии возбуждают наследников :class:`AppError` с ``code`` из реестра контракта (docs/api/rest-api.md);
обработчики из :mod:`vks_common.problem_details` превращают их в ответ RFC 9457.

Это единственный модуль шасси, который разрешено импортировать домену сервисов, поэтому здесь только стандартная
библиотека: доменный слой должен оставаться модулем без зависимостей от фреймворков.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

__all__ = [
    "AppError",
    "Conflict",
    "DependencyUnavailable",
    "Forbidden",
    "InternalError",
    "NotFound",
    "RateLimited",
    "Unauthorized",
    "ValidationFailed",
]


class AppError(Exception):
    """Базовый класс ожидаемых ошибок.

    Наследник объявляет ``code`` (из реестра контракта), ``status`` и ``title`` атрибутами класса::

        class EmailTaken(Conflict):
            code = "email_taken"
            title = "Email is already registered"

    ``detail`` – пояснение для разработчика клиента; пользовательский текст фронтенд выбирает по ``code``.
    ``headers`` уходят в ответ рядом с телом – например, ``Retry-After`` у ``429``.
    """

    code: ClassVar[str] = "internal_error"
    status: ClassVar[int] = 500
    title: ClassVar[str] = "Internal error"

    def __init__(self, detail: str | None = None, *, headers: Mapping[str, str] | None = None) -> None:
        self.detail = detail if detail is not None else self.title
        self.headers: dict[str, str] = dict(headers or {})
        super().__init__(self.detail)


class ValidationFailed(AppError):
    """Запрос не соответствует контракту или бизнес-правилу формата (например, политике пароля).

    ``field`` – имя поля тела запроса: ответ получит ``errors[]`` с ``loc``, как у ошибок схемы, и клиент подсветит
    нужное поле, не разбирая текст.
    """

    code = "validation_error"
    status = 422
    title = "Request is not valid"

    def __init__(
        self,
        detail: str | None = None,
        *,
        field: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail, headers=headers)
        self.field = field


class Unauthorized(AppError):
    """Нет учетных данных или они не проверяются."""

    code = "unauthorized"
    status = 401
    title = "Authentication required"


class Forbidden(AppError):
    """Вызывающий известен, но его роль не разрешает операцию."""

    code = "forbidden"
    status = 403
    title = "Operation is not allowed"


class NotFound(AppError):
    """Ресурса нет или он чужой: ответ не раскрывает, какой из двух случаев."""

    code = "not_found"
    status = 404
    title = "Resource not found"


class Conflict(AppError):
    """Операция противоречит текущему состоянию. Наследники задают свой ``code``."""

    code = "conflict"
    status = 409
    title = "Conflict with the current state"


class RateLimited(AppError):
    """Превышена частота запросов."""

    code = "too_many_requests"
    status = 429
    title = "Too many requests"


class DependencyUnavailable(AppError):
    """Нужная зависимость недоступна после повторов."""

    code = "service_unavailable"
    status = 503
    title = "Dependency is unavailable"


class InternalError(AppError):
    """Непредвиденная ошибка; подробности – только в журнале."""
