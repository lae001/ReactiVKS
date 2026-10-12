"""Фикстуры тестов auth-service.

Схема ``auth`` создается настоящими миграциями под ролью ``auth_svc`` – с теми же правами, что у сервиса в работе.
Каждый тест работает в транзакции, которая откатывается по его окончании.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from auth_service.main import create_application
from auth_service.settings import AuthSettings
from vks_common.clock import FixedClock
from vks_common.config import Environment
from vks_common.db import create_engine, get_session
from vks_common.testing import PostgresServer, app_client, apply_migrations, isolated_session_factory

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def alembic_ini() -> Path:
    return ALEMBIC_INI


@pytest.fixture(scope="session")
def database_url(postgres: PostgresServer) -> str:
    """Адрес роли auth_svc; схема auth доведена до головы миграций."""
    url = postgres.role_url("auth_svc", database=postgres.create_database("auth_test"))
    apply_migrations(alembic_ini=ALEMBIC_INI, database_url=url)
    return url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url, pool_size=2, max_overflow=2)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with isolated_session_factory(engine) as factory:
        yield factory


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def private_key_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Одноразовый ключ подписи на сессию: генерация RSA заметно дорога, а разные ключи тестам не нужны."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path_factory.mktemp("keys") / "jwt-private.pem"
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


@pytest.fixture(scope="session")
def make_settings(private_key_path: Path) -> Callable[..., AuthSettings]:
    """Настройки сервиса без окружения. Argon2 дешевый, чтобы тесты шли быстро."""

    def factory(**overrides: object) -> AuthSettings:
        fields: dict[str, object] = {
            "env": Environment.TEST,
            # Сессии API-тестов подменяются изолированными: адрес нужен только валидации настроек.
            "database_url": "postgresql+asyncpg://auth_svc:unused@localhost:5432/vks",
            "jwt_private_key_path": private_key_path,
            "auth_argon2_time_cost": 1,
            "auth_argon2_memory_kib": 8,
            "auth_argon2_parallelism": 1,
        }
        fields.update(overrides)
        return AuthSettings(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени

    return factory


@pytest.fixture
def settings(make_settings: Callable[..., AuthSettings]) -> AuthSettings:
    return make_settings()


@pytest.fixture
def clock() -> FixedClock:
    """Часы сценариев. Стартуют с настоящего момента: access-токен проверяется по настоящему времени."""
    return FixedClock(datetime.now(UTC))


@pytest.fixture
def app(
    settings: AuthSettings,
    session_factory: async_sessionmaker[AsyncSession],
    clock: FixedClock,
) -> Iterator[FastAPI]:
    """Настоящее приложение на откатываемой БД теста.

    lifespan не запускается (нет сверки схемы и пула): зависимость сессии направлена на изолированную фабрику.
    Остальное – боевой код: роутеры, middleware, обработчики ошибок, сценарии.
    """
    application = create_application(settings)
    application.state.clock = clock

    async def isolated_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = isolated_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Клиент по https: refresh-cookie с атрибутом Secure по http клиент не отправил бы."""
    async with app_client(app, base_url="https://testserver") as http:
        yield http
