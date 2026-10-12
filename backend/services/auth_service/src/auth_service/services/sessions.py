"""Сессии: вход, обмен refresh-токена (ротация), выход.

- Вход проверяет пароль, открывает новую семью refresh-токенов и выдает пару.
- Обмен меняет живой refresh-токен на новую пару в той же семье под блокировкой строки; уже обмененный токен
  отзывает всю семью (признак кражи).
- Выход отзывает семью текущего токена; выданный access-токен действует до истечения срока.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.errors import InvalidCredentials, InvalidEmail
from auth_service.domain.identifiers import RefreshTokenId, SessionFamilyId
from auth_service.domain.passwords import PasswordHasher
from auth_service.domain.sessions import RefreshToken, build_access_claims, hash_refresh_token
from auth_service.domain.signing import TokenSigner
from auth_service.domain.users import User, normalize_email
from auth_service.repositories.refresh_tokens import RefreshTokenRepository
from auth_service.repositories.users import UserRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.ids import new_id, new_token
from vks_common.logging import get_logger

__all__ = ["IssuedSession", "Login", "TokenPolicy"]

_logger = get_logger(__name__)

# User-Agent – справочная информация о сессии; длиннее этого обрезается, чтобы заголовок не раздувал таблицу.
_MAX_USER_AGENT_LENGTH = 512


@dataclass(frozen=True, slots=True)
class TokenPolicy:
    """Чем подписывать и сколько живут токены – из настроек сервиса."""

    issuer: str
    audience: str
    access_ttl: timedelta
    refresh_ttl: timedelta


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Результат входа или обмена. ``refresh_token`` в открытом виде существует только здесь и в cookie ответа."""

    user: User
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


class _SessionIssuer:
    """Выпуск пары – общая часть входа и обмена. Отличаются они только семьей: вход начинает новую."""

    def __init__(self, *, session: AsyncSession, signer: TokenSigner, policy: TokenPolicy) -> None:
        self._tokens = RefreshTokenRepository(session)
        self._signer = signer
        self._policy = policy

    async def issue(
        self,
        *,
        user: User,
        family_id: SessionFamilyId,
        now: datetime,
        user_agent: str | None,
    ) -> tuple[IssuedSession, RefreshTokenId]:
        claims = build_access_claims(
            user=user,
            issuer=self._policy.issuer,
            audience=self._policy.audience,
            token_id=new_id(),
            issued_at=now,
            ttl=self._policy.access_ttl,
        )
        refresh_token = new_token()
        stored = RefreshToken(
            id=RefreshTokenId(new_id()),
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + self._policy.refresh_ttl,
        )
        await self._tokens.add(
            stored,
            user_agent=user_agent[:_MAX_USER_AGENT_LENGTH] if user_agent else None,
            created_at=now,
        )
        issued = IssuedSession(
            user=user,
            access_token=self._signer.sign(claims),
            access_expires_in=int(self._policy.access_ttl.total_seconds()),
            refresh_token=refresh_token,
            refresh_expires_at=stored.expires_at,
        )
        return issued, stored.id


class Login:
    """Вход по e-mail и паролю (UC-1)."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        hasher: PasswordHasher,
        signer: TokenSigner,
        clock: Clock,
        policy: TokenPolicy,
    ) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._hasher = hasher
        self._clock = clock
        self._issuer = _SessionIssuer(session=session, signer=signer, policy=policy)

    async def execute(self, *, email: str, password: str, user_agent: str | None = None) -> IssuedSession:
        # Поиск – в своей короткой транзакции, закрытой до проверки пароля: Argon2 не должен держать соединение.
        async with transaction(self._session):
            user = await self._find(email)

        if user is None:
            await asyncio.to_thread(self._hasher.verify_dummy)
            raise InvalidCredentials()
        if not await asyncio.to_thread(self._hasher.verify, password, user.password_hash):
            raise InvalidCredentials()
        # Блокировка раскрывается только тому, кто знает пароль.
        user.ensure_can_sign_in()

        now = self._clock.now()
        async with transaction(self._session):
            # Вход – новая семья: сессии двух устройств отзываются независимо.
            issued, _ = await self._issuer.issue(
                user=user,
                family_id=SessionFamilyId(new_id()),
                now=now,
                user_agent=user_agent,
            )
            await self._users.record_login(user.id, at=now)

        _logger.info("user signed in", user_id=str(user.id))
        return issued

    async def _find(self, email: str) -> User | None:
        """Неверный формат адреса – не ошибка валидации, а «нет такого пользователя»: иначе ответ отличался бы и по
        коду, и по времени, и по нему можно было бы зондировать сервис."""
        try:
            normalized = normalize_email(email)
        except InvalidEmail:
            return None
        return await self._users.get_by_email(normalized)
