"""Ответы об ошибках в формате RFC 9457 Problem Details (``application/problem+json``).

:func:`install_error_handlers` превращает :class:`~vks_common.errors.AppError` в единый ответ с полем ``code`` и
``request_id`` запроса. Ошибки валидации FastAPI и HTTP-исключения Starlette приводятся к тому же формату;
непредвиденное исключение – ``500 internal_error`` без подробностей в ответе.
"""

from __future__ import annotations

import http
import json
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vks_common.errors import (
    AppError,
    Forbidden,
    InternalError,
    NotFound,
    RateLimited,
    Unauthorized,
    ValidationFailed,
)
from vks_common.logging import current_request_id, get_logger

__all__ = [
    "ERROR_TYPE_BASE",
    "PROBLEM_CONTENT_TYPE",
    "Problem",
    "UnhandledErrorMiddleware",
    "document_problem_responses",
    "install_error_handlers",
    "problem_document",
]

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://vks.example.ru/errors/"

_logger = get_logger(__name__)


def problem_document(
    *,
    code: str,
    status: int,
    title: str,
    detail: str,
    errors: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Тело ответа по RFC 9457.

    Трассировка стека сюда не попадает никогда: сообщение исключения может цитировать запрос, заголовок или
    фрагмент пароля, а тело ответа покидает периметр.
    """
    document: dict[str, object] = {
        "type": f"{ERROR_TYPE_BASE}{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": current_request_id(),
    }
    if errors is not None:
        document["errors"] = errors
    return document


def _response(status: int, document: Mapping[str, object], headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=dict(document),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=dict(headers) if headers else None,
    )


def _log_client_error(request: Request, status: int, code: str) -> None:
    # INFO, а не ERROR: отказ клиенту – нормальная работа, и алерт по доле ошибок не должен на нее срабатывать.
    _logger.info("request refused", http_method=request.method, http_status=status, error_code=code)


async def _app_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, AppError):  # pragma: no cover - FastAPI вызывает обработчик только для AppError
        raise exc
    if exc.status >= 500:
        _logger.error("request failed", exc_info=exc, http_method=request.method, error_code=exc.code)
    else:
        _log_client_error(request, exc.status, exc.code)
    return _response(
        exc.status,
        problem_document(code=exc.code, status=exc.status, title=exc.title, detail=exc.detail),
        exc.headers,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    # Поле input сознательно не возвращается: в нем был бы присланный пароль.
    errors: list[dict[str, object]] = [
        {"loc": list(problem["loc"]), "msg": problem["msg"], "type": problem["type"]} for problem in exc.errors()
    ]
    _log_client_error(request, ValidationFailed.status, ValidationFailed.code)
    return _response(
        ValidationFailed.status,
        problem_document(
            code=ValidationFailed.code,
            status=ValidationFailed.status,
            title=ValidationFailed.title,
            detail="Request does not match the contract",
            errors=errors,
        ),
    )


_CODES_BY_STATUS: dict[int, str] = {
    401: Unauthorized.code,
    403: Forbidden.code,
    404: NotFound.code,
    405: "method_not_allowed",
    422: ValidationFailed.code,
    429: RateLimited.code,
}


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    """Ошибки самой Starlette: неизвестный путь, неразрешенный метод."""
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    status = exc.status_code
    code = _CODES_BY_STATUS.get(status, "http_error")
    title = http.HTTPStatus(status).phrase
    _log_client_error(request, status, code)
    return _response(
        status,
        problem_document(code=code, status=status, title=title, detail=str(exc.detail) or title),
        exc.headers,
    )


class UnhandledErrorMiddleware:
    """Последний рубеж: стек – в журнал, клиенту – ``500 internal_error`` с ``request_id``.

    Middleware, а не ``add_exception_handler(Exception)``: такой обработчик Starlette вешает на самый внешний слой,
    снаружи :class:`~vks_common.middleware.RequestIdMiddleware`, и ответ ушел бы без ``request_id``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as error:
            if response_started:
                # Половину ответа уже не заменить: пусть сервер оборвет соединение.
                raise
            _logger.error(
                "unhandled exception",
                exc_info=error,
                http_method=str(scope.get("method", "")),
                error_code=InternalError.code,
            )
            response = _response(
                InternalError.status,
                problem_document(
                    code=InternalError.code,
                    status=InternalError.status,
                    title=InternalError.title,
                    detail="The service failed to process the request",
                ),
            )
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Подключить обработчики, которые держат все ошибки в одном формате.

    Вызывается до ``add_middleware(RequestIdMiddleware)``: middleware, добавленный позже, оказывается снаружи, и
    непредвиденная ошибка должна перехватываться внутри контекста запроса.
    """
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_middleware(UnhandledErrorMiddleware)


# --- OpenAPI -------------------------------------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """Одна ошибка валидации поля."""

    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """Тело любой ошибки – для документа OpenAPI, по которому фронтенд генерирует типы."""

    model_config = ConfigDict(title="Problem")

    type: str = Field(description="URI описания кода ошибки")
    title: str
    status: int
    detail: str
    code: str = Field(description="Код из реестра контракта – по нему ветвится клиент")
    request_id: str | None = Field(description="Идентификатор запроса для обращения в поддержку")
    errors: list[ValidationIssue] | None = Field(default=None, description="Только у validation_error")


_FASTAPI_ERROR_SCHEMAS = ("HTTPValidationError", "ValidationError")


def document_problem_responses(app: FastAPI) -> None:
    """Сделать так, чтобы OpenAPI описывал ошибки так, как они на самом деле возвращаются.

    FastAPI описывает ``422`` своей схемой ``HTTPValidationError``, а ошибки из ``responses=`` – без тела. Здесь
    каждый ``4xx`` и ``5xx`` становится ``application/problem+json`` со схемой :class:`Problem`.
    """
    generate = app.openapi

    def openapi() -> dict[str, object]:
        if app.openapi_schema is None:
            _describe_problems(generate())
        return app.openapi_schema or {}

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI документирует эту подмену как точку настройки


def _describe_problems(document: dict[str, object]) -> None:
    reference = {"$ref": "#/components/schemas/Problem"}
    paths = document.get("paths")
    for item in paths.values() if isinstance(paths, dict) else ():
        for operation in item.values() if isinstance(item, dict) else ():
            responses = operation.get("responses") if isinstance(operation, dict) else None
            if not isinstance(responses, dict):
                continue
            for status, response in responses.items():
                if str(status)[:1] in {"4", "5"} and isinstance(response, dict):
                    response["content"] = {PROBLEM_CONTENT_TYPE: {"schema": reference}}

    components = document.setdefault("components", {})
    if not isinstance(components, dict):  # pragma: no cover - FastAPI пишет словарь
        return
    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):  # pragma: no cover
        return
    problem_schema = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
    schemas.update(problem_schema.pop("$defs", {}))
    schemas["Problem"] = problem_schema
    for name in _FASTAPI_ERROR_SCHEMAS:
        if f'"#/components/schemas/{name}"' not in json.dumps(document):
            schemas.pop(name, None)
