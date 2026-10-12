"""ASGI-middleware шасси: ``request_id`` и журнал доступа.

Написаны на «сыром» ASGI, а не на ``BaseHTTPMiddleware``: тот выполняет обработчик в отдельной задаче, и
контекстная переменная, выставленная в middleware, не всегда доходит до эндпоинта.
"""

from __future__ import annotations

import re
import time
from uuid import uuid4

from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vks_common.logging import get_logger, request_context

__all__ = ["REQUEST_ID_HEADER", "AccessLogMiddleware", "RequestIdMiddleware"]

REQUEST_ID_HEADER = "x-request-id"

# Чужой request_id принимается, только если похож на идентификатор: значение уходит в журналы и в ответ,
# и строка произвольной длины с управляющими символами туда попасть не должна.
_ACCEPTABLE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_logger = get_logger(__name__)


class RequestIdMiddleware:
    """Принять ``X-Request-ID`` от Nginx или создать новый и вернуть его в ответе.

    Ставится самым внешним: иначе первые записи запроса – самые интересные при сбое – окажутся без идентификатора.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._header = REQUEST_ID_HEADER.encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._incoming(scope) or uuid4().hex

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(name, value) for name, value in message.get("headers", []) if name != self._header]
                headers.append((self._header, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        with request_context(request_id):
            await self.app(scope, receive, send_with_header)

    def _incoming(self, scope: Scope) -> str | None:
        for name, value in scope.get("headers", []):
            if name == self._header:
                candidate = value.decode("latin-1").strip()
                return candidate if _ACCEPTABLE_REQUEST_ID.match(candidate) else None
        return None


class AccessLogMiddleware:
    """Одна структурная запись на запрос: метод, шаблон маршрута, статус, длительность."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # Ожидаемая ошибка клиента – не инцидент: уровень error только у 5xx.
            log = _logger.error if status_code >= 500 else _logger.info
            log(
                "request handled",
                http_method=str(scope.get("method", "")),
                http_path=_route_template(scope),
                http_status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )


def _route_template(scope: Scope) -> str:
    """Шаблон маршрута, а не конкретный URL: идентификатор в пути – это персональные данные и мусор в поиске."""
    route = scope.get("route")
    if isinstance(route, Route):
        return route.path
    return str(scope.get("path", ""))
