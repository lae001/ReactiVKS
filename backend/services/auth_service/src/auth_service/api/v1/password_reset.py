"""Восстановление пароля доступно только при включенном флаге."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.requests import Request

from auth_service.api.v1.dependencies import CurrentClock, Hasher, Session, Settings
from auth_service.services.password_reset import PasswordReset
from vks_common.errors import NotFound

router = APIRouter(prefix="/api/v1/auth/password-reset", tags=["auth"])


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/request", status_code=202)
async def request_reset(
    body: ResetRequest, request: Request, session: Session, settings: Settings, clock: CurrentClock, hasher: Hasher
) -> None:
    if not settings.auth_password_reset_enabled:
        raise NotFound()
    scenario = PasswordReset(session, clock, hasher, request.app.state.reset_mailer)
    await scenario.request(body.email, request.client.host if request.client else "unknown")


@router.post("/confirm", status_code=204)
async def confirm_reset(
    body: ResetConfirm, request: Request, session: Session, settings: Settings, clock: CurrentClock, hasher: Hasher
) -> None:
    if not settings.auth_password_reset_enabled:
        raise NotFound()
    await PasswordReset(session, clock, hasher, request.app.state.reset_mailer).confirm(body.token, body.new_password)
