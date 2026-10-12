"""Структурные журналы: JSON в stdout, один формат для всех сервисов.

Каждая запись содержит ``service``, ``env``, ``level``, ``timestamp`` и поля контекста – ``request_id`` и то, что
сценарий добавил через :func:`bind_context` (``user_id``, ``meeting_id``). Контекст хранится в ``contextvars`` и не
прокидывается вручную.

Сторонние журналы (uvicorn, SQLAlchemy) проходят через тот же форматтер, поэтому каждая строка вывода – JSON.
Что запрещено журналировать – docs/backend/coding-standards.md, §11.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from vks_common.config import Environment, LogLevel

__all__ = [
    "REQUEST_ID_KEY",
    "bind_context",
    "configure_logging",
    "current_request_id",
    "get_logger",
    "request_context",
]

REQUEST_ID_KEY = "request_id"


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Журнал модуля. ``print`` в проекте запрещен – это единственный путь в stdout."""
    return structlog.stdlib.get_logger(name)


def bind_context(**fields: str) -> None:
    """Добавить поля в контекст текущего запроса или сообщения: они попадут в каждую следующую запись."""
    structlog.contextvars.bind_contextvars(**fields)


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    """Начать чистый контекст запроса с этим ``request_id`` и убрать его по выходе.

    Контекст очищается и на входе: соединение keep-alive обслуживает запросы в одной задаче, и поля предыдущего
    запроса не должны перетечь в следующий.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**{REQUEST_ID_KEY: request_id})
    try:
        yield
    finally:
        structlog.contextvars.clear_contextvars()


def current_request_id() -> str | None:
    """``request_id`` текущего запроса или ``None`` вне запроса."""
    value = structlog.contextvars.get_contextvars().get(REQUEST_ID_KEY)
    return value if isinstance(value, str) else None


def _service_context(service_name: str, environment: Environment) -> Processor:
    def add_service_context(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service_name)
        event_dict.setdefault("env", environment.value)
        return event_dict

    return add_service_context


def configure_logging(
    *,
    service_name: str,
    environment: Environment,
    log_level: LogLevel = LogLevel.INFO,
) -> None:
    """Настроить structlog и стандартный logging как один конвейер.

    Идемпотентна: повторный вызов заменяет обработчик, а не добавляет второй (иначе каждая строка удвоится).
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _service_context(service_name, environment),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(sort_keys=True, ensure_ascii=False),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.value)
    # Журнал доступа пишет AccessLogMiddleware с request_id и шаблоном маршрута; запись uvicorn дублировала бы его.
    logging.getLogger("uvicorn.access").disabled = True
