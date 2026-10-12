"""Сборка сценариев для запроса.

Одиночки сервиса (настройки, хешер, ключи, часы) создаются в ``main.py`` и лежат в ``app.state``; здесь они
достаются оттуда и передаются в конструкторы сценариев.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from auth_service.domain.passwords import PasswordHasher
from auth_service.domain.signing import TokenSigner
from auth_service.services.accounts import RegisterOrganizer
from auth_service.services.keys import PublishedKeys
from auth_service.services.profile import GetProfile, RenameUser
from auth_service.services.sessions import Login, Logout, RefreshSession, TokenPolicy
from auth_service.settings import AuthSettings
from vks_common.clock import Clock
from vks_common.db import get_session

__all__ = [
    "CurrentClock",
    "GetProfileScenario",
    "LoginScenario",
    "LogoutScenario",
    "PublishedKeysScenario",
    "RefreshSessionScenario",
    "RegisterOrganizerScenario",
    "RenameUserScenario",
    "Settings",
]


def get_settings(request: Request) -> AuthSettings:
    settings = request.app.state.settings
    if not isinstance(settings, AuthSettings):  # pragma: no cover - выставляет create_application
        raise RuntimeError("в app.state нет настроек auth-service")
    return settings


def get_password_hasher(request: Request) -> PasswordHasher:
    """Хешер, созданный один раз при старте: его конструктор хеширует фиктивный пароль для выравнивания времени."""
    hasher = request.app.state.password_hasher
    if not isinstance(hasher, PasswordHasher):  # pragma: no cover - выставляет create_application
        raise RuntimeError("в app.state нет password_hasher")
    return hasher


def get_token_signer(request: Request) -> TokenSigner:
    """Ключ подписи – закрытый ключ живет в этом объекте и больше нигде."""
    signer = request.app.state.token_signer
    if not isinstance(signer, TokenSigner):  # pragma: no cover - выставляет create_application
        raise RuntimeError("в app.state нет token_signer")
    return signer


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


Settings = Annotated[AuthSettings, Depends(get_settings)]
Hasher = Annotated[PasswordHasher, Depends(get_password_hasher)]
Signer = Annotated[TokenSigner, Depends(get_token_signer)]
CurrentClock = Annotated[Clock, Depends(get_clock)]
Session = Annotated[AsyncSession, Depends(get_session)]


def build_published_keys(signer: Signer) -> PublishedKeys:
    return PublishedKeys(signer)


PublishedKeysScenario = Annotated[PublishedKeys, Depends(build_published_keys)]


def build_register_organizer(
    session: Session, hasher: Hasher, clock: CurrentClock, settings: Settings
) -> RegisterOrganizer:
    return RegisterOrganizer(
        session=session,
        hasher=hasher,
        clock=clock,
        registration_enabled=settings.auth_registration_enabled,
    )


RegisterOrganizerScenario = Annotated[RegisterOrganizer, Depends(build_register_organizer)]


def get_token_policy(settings: Settings) -> TokenPolicy:
    return TokenPolicy(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_ttl=timedelta(seconds=settings.auth_access_token_ttl_seconds),
        refresh_ttl=timedelta(days=settings.auth_refresh_token_ttl_days),
    )


Policy = Annotated[TokenPolicy, Depends(get_token_policy)]


def build_login(session: Session, hasher: Hasher, signer: Signer, clock: CurrentClock, policy: Policy) -> Login:
    return Login(session=session, hasher=hasher, signer=signer, clock=clock, policy=policy)


LoginScenario = Annotated[Login, Depends(build_login)]


def build_refresh_session(session: Session, signer: Signer, clock: CurrentClock, policy: Policy) -> RefreshSession:
    return RefreshSession(session=session, signer=signer, clock=clock, policy=policy)


def build_logout(session: Session, clock: CurrentClock) -> Logout:
    return Logout(session=session, clock=clock)


RefreshSessionScenario = Annotated[RefreshSession, Depends(build_refresh_session)]
LogoutScenario = Annotated[Logout, Depends(build_logout)]


def build_get_profile(session: Session) -> GetProfile:
    return GetProfile(session=session)


def build_rename_user(session: Session, clock: CurrentClock) -> RenameUser:
    return RenameUser(session=session, clock=clock)


GetProfileScenario = Annotated[GetProfile, Depends(build_get_profile)]
RenameUserScenario = Annotated[RenameUser, Depends(build_rename_user)]
