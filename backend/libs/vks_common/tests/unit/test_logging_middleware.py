import json
import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from vks_common.config import Environment
from vks_common.logging import bind_context, configure_logging, current_request_id, get_logger
from vks_common.middleware import AccessLogMiddleware, RequestIdMiddleware


@pytest.fixture(autouse=True)
def detach_log_handlers() -> Iterator[None]:
    """configure_logging привязывает обработчик к sys.stdout теста – capsys закроет этот поток после теста."""
    yield
    logging.getLogger().handlers.clear()


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str | None]:
        bind_context(user_id="u-1")
        get_logger("test").info("item read")
        return {"request_id": current_request_id()}

    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url="http://test")


def log_records(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


async def test_incoming_request_id_is_kept_and_returned() -> None:
    async with client() as http:
        response = await http.get("/items/1", headers={"X-Request-ID": "nginx-abc.123"})

    assert response.headers["x-request-id"] == "nginx-abc.123"
    assert response.json() == {"request_id": "nginx-abc.123"}


async def test_request_id_is_generated_when_absent() -> None:
    async with client() as http:
        response = await http.get("/items/1")

    assert len(response.headers["x-request-id"]) == 32


async def test_malformed_request_id_is_replaced() -> None:
    async with client() as http:
        response = await http.get("/items/1", headers={"X-Request-ID": "bad id\twith spaces"})

    assert response.headers["x-request-id"] != "bad id\twith spaces"
    assert len(response.headers["x-request-id"]) == 32


async def test_records_carry_request_context_and_route_template(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(service_name="example", environment=Environment.TEST)

    async with client() as http:
        await http.get("/items/0192-secret-id", headers={"X-Request-ID": "req-1"})

    records = log_records(capsys.readouterr().out)
    item_read = next(record for record in records if record["event"] == "item read")
    access = next(record for record in records if record["event"] == "request handled")
    assert item_read["request_id"] == "req-1"
    assert item_read["user_id"] == "u-1"
    assert item_read["service"] == "example"
    assert access["http_path"] == "/items/{item_id}"
    assert access["http_status"] == 200


async def test_context_does_not_leak_between_requests(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(service_name="example", environment=Environment.TEST)

    async with client() as http:
        await http.get("/items/1", headers={"X-Request-ID": "first"})
        await http.get("/items/2", headers={"X-Request-ID": "second"})

    assert current_request_id() is None
    request_ids = [record["request_id"] for record in log_records(capsys.readouterr().out) if "request_id" in record]
    assert request_ids.count("first") == 2
    assert request_ids.count("second") == 2
