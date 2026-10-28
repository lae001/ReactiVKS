"""Фикстуры тестов meeting-service.

Схема ``meeting`` создается настоящими миграциями под ролью ``meeting_svc`` – с теми же правами, что у сервиса в
работе. Каждый тест работает в транзакции, которая откатывается по его окончании.
"""

import base64
import hashlib
import itertools
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from google.protobuf.json_format import MessageToJson
from livekit import api
from livekit.protocol.models import DisconnectReason, ParticipantInfo, Room
from livekit.protocol.webhook import WebhookEvent
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from meeting_service.domain.errors import LiveKitUnavailable
from meeting_service.domain.livekit import MediaKind, RoomAccess
from meeting_service.main import create_application
from meeting_service.settings import MeetingSettings
from vks_common.auth import use_authentication
from vks_common.clock import FixedClock
from vks_common.config import Environment
from vks_common.db import create_engine, get_session
from vks_common.testing import PostgresServer, TokenFactory, app_client, apply_migrations, isolated_session_factory

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
DATABASE = "meeting_test"


@pytest.fixture(scope="session")
def alembic_ini() -> Path:
    return ALEMBIC_INI


@pytest.fixture(scope="session")
def database_url(postgres: PostgresServer) -> str:
    """Адрес роли meeting_svc; схема meeting доведена до головы миграций."""
    url = postgres.role_url("meeting_svc", database=postgres.create_database(DATABASE))
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


class FakeLiveKitGateway:
    """Подмена LiveKit – внешней границы сервиса (coding-standards.md, §14).

    Запоминает созданные и закрытые комнаты; токен – читаемая строка с тем, что в нем было бы подписано.
    ``available = False`` изображает LiveKit, не ответивший после повторов.
    """

    public_url = "ws://livekit.test:7880"

    def __init__(self) -> None:
        self.available = True
        self.rooms: set[str] = set()
        self.deleted: list[str] = []
        self.issued: list[RoomAccess] = []
        self.muted: list[tuple[str, str, MediaKind]] = []
        self.removed: list[tuple[str, str]] = []

    async def ensure_room(self, room: str) -> None:
        if not self.available:
            raise LiveKitUnavailable()
        self.rooms.add(room)

    async def delete_room(self, room: str) -> None:
        if not self.available:
            raise LiveKitUnavailable()
        self.rooms.discard(room)
        self.deleted.append(room)

    def issue_token(self, access: RoomAccess) -> str:
        self.issued.append(access)
        return f"lk:{access.room}:{access.identity}:{access.attributes['vks.consent']}"

    async def mute(self, room: str, identity: str, kind: MediaKind) -> None:
        if not self.available:
            raise LiveKitUnavailable()
        self.muted.append((room, identity, kind))

    async def remove(self, room: str, identity: str) -> None:
        if not self.available:
            raise LiveKitUnavailable()
        self.removed.append((room, identity))


@pytest.fixture
def livekit() -> FakeLiveKitGateway:
    return FakeLiveKitGateway()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 20, 7, 0, tzinfo=UTC))


@pytest.fixture(scope="session")
def tokens() -> TokenFactory:
    """Ключ подписи access-токенов на сессию: генерация RSA дорогая, а разные ключи тестам не нужны."""
    return TokenFactory()


@pytest.fixture
def settings() -> MeetingSettings:
    return MeetingSettings(
        env=Environment.TEST,
        # Сессии API-тестов подменяются изолированными: адрес нужен только валидации настроек.
        database_url="postgresql+asyncpg://meeting_svc:unused@localhost:5432/vks",
        public_base_url="https://vks.example.ru",
        livekit_api_key="devkey",
        livekit_api_secret=SecretStr("test-secret-0123456789abcdef0123456789"),
    )


@pytest.fixture
def app(
    settings: MeetingSettings,
    session_factory: async_sessionmaker[AsyncSession],
    clock: FixedClock,
    livekit: FakeLiveKitGateway,
    tokens: TokenFactory,
) -> Iterator[FastAPI]:
    """Настоящее приложение на откатываемой БД теста.

    lifespan не запускается: шлюз LiveKit и проверка токенов подменены, сессия направлена на изолированную фабрику.
    Остальное – боевой код: роутеры, middleware, обработчики ошибок, сценарии, репозитории.
    """
    application = create_application(settings)
    application.state.clock = clock
    application.state.livekit = livekit
    use_authentication(application, tokens.verifier())

    async def isolated_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = isolated_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app_client(app) as http:
        yield http


OrganizerHeaders = Callable[..., dict[str, str]]


@pytest.fixture
def organizer_headers(tokens: TokenFactory) -> OrganizerHeaders:
    """Заголовок Bearer организатора; без аргумента – каждый раз новый организатор."""

    def headers(user_id: UUID | None = None, *, name: str = "Иван Петров") -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens.issue(user_id=user_id or uuid4(), name=name)}"}

    return headers


class LiveKitWebhooks:
    """Вебхуки LiveKit, подписанные как их подписывает сервер: JWT ключом API с SHA-256 тела.

    Каждое событие получает свой ``id`` и момент на секунду позже предыдущего – как последовательность в комнате.
    """

    def __init__(self, client: httpx.AsyncClient, settings: MeetingSettings) -> None:
        self._client = client
        self._api_key = settings.livekit_api_key
        self._api_secret = settings.livekit_api_secret.get_secret_value()
        self._sequence = itertools.count(1)
        self._started = int(datetime(2026, 11, 20, 7, 0, tzinfo=UTC).timestamp())

    def body(
        self,
        event: str,
        *,
        room: str,
        identity: str | None = None,
        event_id: str | None = None,
        created_at: int | None = None,
        is_agent: bool = False,
        disconnect_reason: int = DisconnectReason.CLIENT_INITIATED,
    ) -> str:
        number = next(self._sequence)
        message = WebhookEvent(
            event=event,
            id=event_id or f"EV_{uuid4().hex[:12]}",
            created_at=created_at if created_at is not None else self._started + number,
            room=Room(name=room),
        )
        if identity is not None:
            message.participant.CopyFrom(
                ParticipantInfo(
                    identity=identity,
                    kind=ParticipantInfo.Kind.AGENT if is_agent else ParticipantInfo.Kind.STANDARD,
                    disconnect_reason=disconnect_reason,  # type: ignore[arg-type]  # protobuf-перечисление – int
                )
            )
        return MessageToJson(message)

    def sign(self, body: str) -> str:
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        return api.AccessToken(self._api_key, self._api_secret).with_sha256(digest).to_jwt()

    async def post(self, body: str, *, authorization: str | None = None) -> httpx.Response:
        return await self._client.post(
            "/webhooks/livekit",
            content=body,
            headers={"Authorization": authorization or self.sign(body), "Content-Type": "application/webhook+json"},
        )

    async def send(self, event: str, **fields: object) -> httpx.Response:
        response = await self.post(self.body(event, **fields))  # type: ignore[arg-type]  # поля body по имени
        assert response.status_code == 204, response.text
        return response


@pytest.fixture
def webhooks(client: httpx.AsyncClient, settings: MeetingSettings) -> LiveKitWebhooks:
    return LiveKitWebhooks(client, settings)
