"""HTTP-клиент к приложению в том же процессе."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

__all__ = ["app_client"]


def app_client(app: FastAPI, *, base_url: str = "http://testserver") -> httpx.AsyncClient:
    """Клиент, который ходит в приложение через ASGI, без сокета и порта.

    Middleware, обработчики ошибок и зависимости – настоящие. ``raise_app_exceptions=False``: непредвиденная ошибка
    проверяется по ответу ``500``, как ее увидит клиент.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url=base_url)
