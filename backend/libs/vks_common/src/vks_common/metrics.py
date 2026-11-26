"""HTTP-метрики с шаблонами маршрутов вместо пользовательских URL."""

from time import monotonic

from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestMetrics:
    def __init__(self, app: ASGIApp, registry: CollectorRegistry) -> None:
        self.app = app
        self.requests = Counter(
            "http_requests_total", "HTTP responses", ["method", "route", "status"], registry=registry
        )
        self.duration = Histogram(
            "http_request_duration_seconds", "HTTP latency", ["method", "route"], registry=registry
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        started, status = monotonic(), 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            method = (
                scope["method"]
                if scope["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                else "OTHER"
            )
            self.requests.labels(method, route, str(status)).inc()
            self.duration.labels(method, route).observe(monotonic() - started)
