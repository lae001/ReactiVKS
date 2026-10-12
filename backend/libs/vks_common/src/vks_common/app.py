"""Фабрика приложения: все, что у сервисов общее, собирается один раз.

Сервису остаются настройки, роутеры и свой ``lifespan``::

    app = create_app(settings, routers=[auth_router, users_router], lifespan=lifespan, title="ReactiVKS Auth")

В ответ он получает ``request_id`` и журнал доступа, ошибки RFC 9457, ``/health`` и ``/ready`` (conventions.md,
§10) и закрытие пула БД при остановке. ``/health``, ``/ready`` и ``/docs`` Nginx наружу не проксирует.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import APIRouter, FastAPI, status
from fastapi.responses import JSONResponse

from vks_common.config import BaseServiceSettings
from vks_common.db.session import Database
from vks_common.logging import configure_logging, get_logger
from vks_common.middleware import AccessLogMiddleware, RequestIdMiddleware
from vks_common.problem_details import document_problem_responses, install_error_handlers

__all__ = ["HealthRegistry", "ReadinessCheck", "ServiceLifespan", "create_app", "use_database"]

ServiceLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]
ReadinessCheck = Callable[[], Awaitable[None]]

_logger = get_logger(__name__)


class HealthRegistry:
    """Проверки зависимостей для ``/ready``.

    Некритичная зависимость (Kafka для auth: события копятся в outbox) показывается в ответе, но не делает сервис
    неготовым.
    """

    def __init__(self) -> None:
        self._checks: dict[str, tuple[ReadinessCheck, bool]] = {}

    def register(self, name: str, check: ReadinessCheck, *, critical: bool = True) -> None:
        self._checks[name] = (check, critical)

    async def run(self, *, timeout_seconds: float) -> tuple[bool, dict[str, str]]:
        """Выполнить проверки параллельно, каждую со своим таймаутом."""
        names = list(self._checks)
        outcomes = await asyncio.gather(*(self._probe(name, timeout_seconds) for name in names))
        results = dict(zip(names, outcomes, strict=True))
        is_ready = all(results[name] == "ok" for name in names if self._checks[name][1])
        return is_ready, results

    async def _probe(self, name: str, timeout_seconds: float) -> str:
        check, _ = self._checks[name]
        try:
            async with asyncio.timeout(timeout_seconds):
                await check()
        except Exception as error:  # noqa: BLE001 - любая ошибка зависимости означает «недоступна»
            _logger.warning("readiness check failed", check=name, error=type(error).__name__)
            return "unavailable"
        return "ok"


def use_database(app: FastAPI, database: Database) -> None:
    """Подключить БД: туда, где ее ищет ``get_session``, и в проверки ``/ready``."""
    app.state.database = database
    health: HealthRegistry = app.state.health
    health.register("postgres", database.check)


def create_app(
    settings: BaseServiceSettings,
    *,
    routers: Sequence[APIRouter] = (),
    lifespan: ServiceLifespan | None = None,
    title: str | None = None,
) -> FastAPI:
    """Собрать приложение FastAPI сервиса."""
    configure_logging(service_name=settings.service_name, environment=settings.env, log_level=settings.log_level)
    health = HealthRegistry()

    @asynccontextmanager
    async def chassis_lifespan(app: FastAPI) -> AsyncIterator[None]:
        _logger.info("service starting", version=settings.service_version)
        try:
            if lifespan is None:
                yield
            else:
                async with lifespan(app):
                    yield
        finally:
            database = getattr(app.state, "database", None)
            if isinstance(database, Database):
                await database.dispose()
            _logger.info("service stopped")

    app = FastAPI(
        title=title or settings.service_name,
        version=settings.service_version,
        lifespan=chassis_lifespan,
        # Swagger UI – только вне production (rest-api.md); OpenAPI-документ нужен фронтенду для генерации типов.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.health = health

    # Порядок важен: middleware, добавленный позже, оказывается снаружи. Снаружи внутрь: request_id → журнал
    # доступа → перехват непредвиденных ошибок (его добавляет install_error_handlers) → маршруты.
    install_error_handlers(app)
    document_problem_responses(app)
    app.include_router(_health_router(settings, health))
    for router in routers:
        app.include_router(router)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


def _health_router(settings: BaseServiceSettings, health: HealthRegistry) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.get("/health")
    async def liveness() -> dict[str, str]:
        """Процесс жив. Зависимости не проверяются: их сбой – повод не слать трафик, а не перезапускать процесс."""
        return {"status": "ok", "service": settings.service_name, "version": settings.service_version}

    @router.get("/ready")
    async def readiness() -> JSONResponse:
        """Готов ли сервис обслуживать запросы: критичные зависимости отвечают."""
        is_ready, checks = await health.run(timeout_seconds=settings.ready_check_timeout_seconds)
        return JSONResponse(
            status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ok" if is_ready else "unavailable", "checks": checks},
        )

    return router
