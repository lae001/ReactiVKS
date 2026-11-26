"""Восстановление пароля без раскрытия существования адреса."""

import asyncio
import hashlib
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.passwords import PasswordHasher, check_password_policy
from auth_service.domain.reset import InvalidResetToken, ResetDeliveryError, ResetMailer
from auth_service.domain.sessions import hash_refresh_token
from auth_service.domain.users import normalize_email
from auth_service.repositories.password_reset import ResetRepository
from auth_service.repositories.refresh_tokens import RefreshTokenRepository
from auth_service.repositories.users import UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.errors import RateLimited
from vks_common.logging import get_logger

_logger = get_logger(__name__)


class PasswordReset:
    def __init__(self, session: AsyncSession, clock: Clock, hasher: PasswordHasher, mailer: ResetMailer) -> None:
        self.session = session
        self.clock = clock
        self.hasher = hasher
        self.mailer = mailer

    async def request(self, email: str, ip: str) -> None:
        email = normalize_email(email)
        now = self.clock.now()
        repository = ResetRepository(self.session)
        token = secrets.token_urlsafe(32)
        async with transaction(self.session):
            keys = ["email:" + email, "ip:" + ip]
            allowed = [await repository.allow(hashlib.sha256(key.encode()).hexdigest(), now) for key in keys]
            if not all(allowed):
                raise RateLimited(headers={"Retry-After": "60"})
            user = await UserRepository(self.session).get_by_email(email)
            if user is not None and not user.is_blocked:
                await repository.add(hash_refresh_token(token), user.id, now)
        if user is not None and not user.is_blocked:
            try:
                await self.mailer.send(user.email, token)
            except ResetDeliveryError:
                _logger.error("password reset delivery failed")

    async def confirm(self, token: str, password: str) -> None:
        check_password_policy(password, field="new_password")
        password_hash = await asyncio.to_thread(self.hasher.hash, password)
        now = self.clock.now()
        repository = ResetRepository(self.session)
        async with transaction(self.session):
            user_id = await repository.user_for_token(hash_refresh_token(token), now)
            user = await UserRepository(self.session).get_by_id(user_id) if user_id else None
            if user is None or user.is_blocked:
                raise InvalidResetToken()
            await UserRepository(self.session).change_password_hash(user.id, password_hash, now=now)
            await repository.consume_all(user.id, now)
            await RefreshTokenRepository(self.session).revoke_all_for_user(user.id, at=now)
