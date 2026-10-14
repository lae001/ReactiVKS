"""Гонка двух одновременных обменов одного refresh-токена.

Нужны настоящие параллельные транзакции на разных соединениях: точки сохранения одной откатываемой транзакции
гонку не покажут. Поэтому сессии здесь коммитят по-настоящему, а тест сам удаляет созданного пользователя (его
токены удаляются каскадно).
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from auth_service.adapters.argon2_hasher import Argon2Hasher
from auth_service.adapters.rsa_keys import RsaKeyRing
from auth_service.domain.errors import SessionInvalid
from auth_service.services.accounts import RegisterOrganizer
from auth_service.services.sessions import IssuedSession, Login, RefreshSession, TokenPolicy
from auth_service.settings import AuthSettings
from vks_common.clock import SystemClock
from vks_common.db import create_session_factory

pytestmark = pytest.mark.integration

POLICY = TokenPolicy(
    issuer="vks-auth", audience="vks", access_ttl=timedelta(minutes=15), refresh_ttl=timedelta(days=30)
)
PASSWORD = "correct-horse-7"


@pytest.fixture
async def committing_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = create_session_factory(engine)
    yield factory
    async with factory() as session:
        await session.execute(text("DELETE FROM auth.users WHERE email LIKE 'race-%'"))
        await session.commit()


async def test_only_one_of_two_concurrent_refreshes_succeeds(
    committing_factory: async_sessionmaker[AsyncSession],
    settings: AuthSettings,
    hasher: Argon2Hasher,
) -> None:
    signer = RsaKeyRing(settings.read_private_key_pem())
    clock = SystemClock()
    email = f"race-{datetime.now(UTC).timestamp()}@example.ru"
    async with committing_factory() as session:
        await RegisterOrganizer(session=session, hasher=hasher, clock=clock, registration_enabled=True).execute(
            email=email, password=PASSWORD, display_name="Гонка"
        )
    async with committing_factory() as session:
        issued = await Login(session=session, hasher=hasher, signer=signer, clock=clock, policy=POLICY).execute(
            email=email, password=PASSWORD
        )

    async def exchange() -> IssuedSession | SessionInvalid:
        async with committing_factory() as session:
            scenario = RefreshSession(session=session, signer=signer, clock=clock, policy=POLICY)
            try:
                return await scenario.execute(refresh_token=issued.refresh_token)
            except SessionInvalid as error:
                return error

    outcomes = await asyncio.gather(exchange(), exchange())

    winners = [outcome for outcome in outcomes if isinstance(outcome, IssuedSession)]
    assert len(winners) == 1
    # Проигравший предъявил уже обмененный токен – это повторное использование: вся семья отозвана, и токен
    # победителя тоже больше не действует.
    async with committing_factory() as session:
        scenario = RefreshSession(session=session, signer=signer, clock=clock, policy=POLICY)
        with pytest.raises(SessionInvalid):
            await scenario.execute(refresh_token=winners[0].refresh_token)
