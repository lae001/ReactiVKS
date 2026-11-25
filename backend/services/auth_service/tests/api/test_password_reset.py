"""Восстановление: флаг, одноразовость, лимит и отзыв refresh-сессий."""

from collections.abc import Awaitable, Callable

import httpx
import pytest
from fastapi import FastAPI

from auth_service.domain.users import User
from auth_service.settings import AuthSettings

pytestmark = pytest.mark.integration


class Mailbox:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send(self, email: str, token: str) -> None:
        self.messages.append((email, token))


async def test_reset_disabled(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/password-reset/request", json={"email": "x@example.ru"})).status_code == 404


async def test_reset_single_use_and_revokes_sessions(
    client: httpx.AsyncClient, app: FastAPI, settings: AuthSettings, make_user: Callable[..., Awaitable[User]]
) -> None:
    app.state.settings = settings.model_copy(update={"auth_password_reset_enabled": True})
    mailbox = Mailbox()
    app.state.reset_mailer = mailbox
    user = await make_user()
    login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse-7"})
    assert login.status_code == 200
    request = await client.post("/api/v1/auth/password-reset/request", json={"email": user.email})
    assert request.status_code == 202
    assert len(mailbox.messages) == 1
    assert (await client.post("/api/v1/auth/password-reset/request", json={"email": user.email})).status_code == 429
    token = mailbox.messages[0][1]
    body = {"token": token, "new_password": "battery-staple-9"}
    assert (await client.post("/api/v1/auth/password-reset/confirm", json=body)).status_code == 204
    assert (await client.post("/api/v1/auth/password-reset/confirm", json=body)).status_code == 400
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json={"email": user.email, "password": body["new_password"]})
    ).status_code == 200


async def test_unknown_email_is_accepted_without_mail(
    client: httpx.AsyncClient, app: FastAPI, settings: AuthSettings
) -> None:
    app.state.settings = settings.model_copy(update={"auth_password_reset_enabled": True})
    mailbox = Mailbox()
    app.state.reset_mailer = mailbox
    assert (
        await client.post("/api/v1/auth/password-reset/request", json={"email": "missing@example.ru"})
    ).status_code == 202
    assert mailbox.messages == []


async def test_delivery_failure_does_not_reveal_existing_account(
    client: httpx.AsyncClient, app: FastAPI, settings: AuthSettings, make_user: Callable[..., Awaitable[User]]
) -> None:
    from auth_service.domain.reset import ResetDeliveryError

    class FailedMailbox:
        async def send(self, email: str, token: str) -> None:
            raise ResetDeliveryError()

    app.state.settings = settings.model_copy(update={"auth_password_reset_enabled": True})
    app.state.reset_mailer = FailedMailbox()
    user = await make_user()
    response = await client.post("/api/v1/auth/password-reset/request", json={"email": user.email})
    assert response.status_code == 202
