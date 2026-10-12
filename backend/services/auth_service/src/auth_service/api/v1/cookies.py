"""Refresh-cookie по контракту: ``vks_refresh``, ``HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth``.

Cookie видна только эндпоинтам ``/api/v1/auth`` – остальным запросам она не уходит, а ``SameSite=Strict`` закрывает
CSRF (05-security-privacy.md).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

__all__ = [
    "REFRESH_COOKIE",
    "REFRESH_COOKIE_PATH",
    "clear_refresh_cookie",
    "cleared_refresh_cookie_header",
    "set_refresh_cookie",
]

REFRESH_COOKIE = "vks_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str, *, expires_at: datetime, now: datetime, secure: bool) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max(int((expires_at - now).total_seconds()), 0),
        path=REFRESH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=secure, httponly=True, samesite="strict")


def cleared_refresh_cookie_header(*, secure: bool) -> str:
    """Значение ``Set-Cookie``, стирающее cookie, – для ответа об ошибке, который строит обработчик шасси."""
    response = Response()
    clear_refresh_cookie(response, secure=secure)
    return response.headers["set-cookie"]
