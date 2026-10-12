import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from vks_common.app import HealthRegistry, create_app
from vks_common.config import BaseServiceSettings, Environment
from vks_common.errors import NotFound
from vks_common.testing import app_client


class ExampleSettings(BaseServiceSettings):
    service_name: str = "example"


def build_app(*, env: Environment = Environment.TEST) -> FastAPI:
    router = APIRouter(prefix="/api/v1")

    @router.get("/things/{thing_id}")
    async def read_thing(thing_id: str) -> None:
        raise NotFound()

    return create_app(ExampleSettings(env=env, ready_check_timeout_seconds=0.1), routers=[router])


async def test_health_reports_service_and_version() -> None:
    async with app_client(build_app()) as http:
        response = await http.get("/health")

    assert response.json() == {"status": "ok", "service": "example", "version": "0.1.0"}


async def test_ready_is_ok_when_critical_checks_pass() -> None:
    app = build_app()

    async def healthy() -> None:
        return None

    health: HealthRegistry = app.state.health
    health.register("postgres", healthy)

    async with app_client(app) as http:
        response = await http.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok"}}


async def test_ready_is_503_when_critical_check_fails_or_hangs() -> None:
    app = build_app()

    async def failing() -> None:
        raise ConnectionRefusedError

    async def hanging() -> None:
        await asyncio.sleep(10)

    health: HealthRegistry = app.state.health
    health.register("postgres", failing)
    health.register("redis", hanging)

    async with app_client(app) as http:
        response = await http.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "unavailable", "redis": "unavailable"}


async def test_non_critical_failure_does_not_make_service_unready() -> None:
    app = build_app()

    async def failing() -> None:
        raise ConnectionRefusedError

    health: HealthRegistry = app.state.health
    health.register("kafka", failing, critical=False)

    async with app_client(app) as http:
        response = await http.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"kafka": "unavailable"}


async def test_routers_get_request_id_and_problem_details() -> None:
    async with app_client(build_app()) as http:
        response = await http.get("/api/v1/things/1", headers={"X-Request-ID": "req-7"})

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "req-7"
    assert response.json()["request_id"] == "req-7"


async def test_swagger_ui_is_off_in_production() -> None:
    async with app_client(build_app(env=Environment.PRODUCTION)) as http:
        docs = await http.get("/docs")
        openapi = await http.get("/openapi.json")

    assert docs.status_code == 404
    assert openapi.status_code == 200


async def test_service_lifespan_runs_inside_chassis_lifespan() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        events.append("started")
        yield
        events.append("stopped")

    app = create_app(ExampleSettings(), lifespan=lifespan)

    async with app.router.lifespan_context(app):
        events.append("serving")

    assert events == ["started", "serving", "stopped"]
