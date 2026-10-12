import httpx
from fastapi import FastAPI, status
from pydantic import BaseModel

from vks_common.errors import Conflict, RateLimited, ValidationFailed
from vks_common.middleware import RequestIdMiddleware
from vks_common.problem_details import (
    PROBLEM_CONTENT_TYPE,
    document_problem_responses,
    install_error_handlers,
)


class EmailTaken(Conflict):
    code = "email_taken"
    title = "Email is already registered"


class Credentials(BaseModel):
    email: str
    password: str


def build_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    document_problem_responses(app)

    @app.post("/register", status_code=status.HTTP_201_CREATED, responses={409: {"description": "Занято"}})
    async def register(body: Credentials) -> Credentials:
        raise EmailTaken("This email is already registered")

    @app.get("/limited")
    async def limited() -> None:
        raise RateLimited(headers={"Retry-After": "30"})

    @app.post("/password")
    async def change_password() -> None:
        raise ValidationFailed("Password must contain a digit", field="new_password")

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("connection string postgresql://user:secret@db leaked")

    app.add_middleware(RequestIdMiddleware)
    return app


def client() -> httpx.AsyncClient:
    # raise_app_exceptions=False: Starlette после ответа 500 пробрасывает исключение дальше, а тест проверяет ответ.
    transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Request-ID": "req-42"})


async def test_app_error_becomes_problem_with_code_and_request_id() -> None:
    async with client() as http:
        response = await http.post("/register", json={"email": "a@b.ru", "password": "x"})

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert response.json() == {
        "type": "https://vks.example.ru/errors/email_taken",
        "title": "Email is already registered",
        "status": 409,
        "detail": "This email is already registered",
        "code": "email_taken",
        "request_id": "req-42",
    }


async def test_error_headers_reach_the_response() -> None:
    async with client() as http:
        response = await http.get("/limited")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json()["code"] == "too_many_requests"


async def test_validation_error_lists_fields_without_echoing_input() -> None:
    async with client() as http:
        response = await http.post("/register", json={"password": "my-secret-password"})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["errors"] == [{"loc": ["body", "email"], "msg": "Field required", "type": "missing"}]
    assert "my-secret-password" not in response.text


async def test_unknown_path_is_problem_not_found() -> None:
    async with client() as http:
        response = await http.get("/nowhere")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_wrong_method_is_problem_method_not_allowed() -> None:
    async with client() as http:
        response = await http.delete("/register")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


async def test_unexpected_exception_is_500_without_details() -> None:
    async with client() as http:
        response = await http.get("/broken")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.json()["request_id"] == "req-42"
    assert "secret" not in response.text


async def test_openapi_describes_errors_as_problem_documents() -> None:
    async with client() as http:
        document = (await http.get("/openapi.json")).json()

    responses = document["paths"]["/register"]["post"]["responses"]
    assert responses["409"]["content"] == {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}}
    assert responses["422"]["content"] == responses["409"]["content"]
    assert "HTTPValidationError" not in document["components"]["schemas"]
    assert "Problem" in document["components"]["schemas"]


async def test_domain_validation_error_points_to_field() -> None:
    async with client() as http:
        response = await http.post("/password")

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"loc": ["body", "new_password"], "msg": "Password must contain a digit", "type": "value_error"}
    ]
