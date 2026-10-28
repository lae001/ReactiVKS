from collections.abc import AsyncIterator
from datetime import timedelta

import aiohttp
import jwt
import pytest

from meeting_service.adapters.livekit_server import LiveKitServerGateway
from meeting_service.domain.errors import LiveKitUnavailable
from meeting_service.domain.livekit import RoomAccess

API_KEY = "devkey"
API_SECRET = "test-secret-0123456789abcdef0123456789"
# Порт 1 на localhost закрыт: соединение отвергается сразу, без ожидания таймаута.
CLOSED_PORT_URL = "http://127.0.0.1:1"


@pytest.fixture
async def gateway() -> AsyncIterator[LiveKitServerGateway]:
    gateway = LiveKitServerGateway(
        url=CLOSED_PORT_URL,
        public_url="ws://localhost:7880",
        api_key=API_KEY,
        api_secret=API_SECRET,
        token_ttl=timedelta(hours=6),
        timeout_seconds=1.0,
        retry_delays=(0.0, 0.0),
    )
    yield gateway
    await gateway.aclose()


async def test_token_grants_joining_one_room_without_changing_own_attributes(gateway: LiveKitServerGateway) -> None:
    access = RoomAccess(
        room="0192-room",
        identity="p_0192",
        name="Анна",
        attributes={"vks.role": "guest", "vks.consent": "granted", "vks.kind": "human"},
    )

    token = gateway.issue_token(access)

    claims = jwt.decode(token, API_SECRET, algorithms=["HS256"], options={"verify_aud": False})
    assert claims["iss"] == API_KEY
    assert claims["sub"] == "p_0192"
    assert claims["name"] == "Анна"
    assert claims["exp"] - claims["nbf"] == pytest.approx(6 * 3600, abs=120)
    assert claims["attributes"] == {"vks.role": "guest", "vks.consent": "granted", "vks.kind": "human"}
    video = claims["video"]
    assert video["room"] == "0192-room"
    assert video["roomJoin"] is True
    assert video["canUpdateOwnMetadata"] is False
    assert video["canPublishSources"] == ["camera", "microphone", "screen_share", "screen_share_audio"]


async def test_unreachable_livekit_is_reported_after_retries(gateway: LiveKitServerGateway) -> None:
    with pytest.raises(LiveKitUnavailable) as raised:
        await gateway.ensure_room("0192-room")

    assert isinstance(raised.value.__cause__, aiohttp.ClientError)


async def test_transient_failure_is_retried(gateway: LiveKitServerGateway) -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise aiohttp.ClientConnectionError("connection reset")
        return "ok"

    # Политика повторов проверяется на самом цикле повторов: сетевой сбой на настоящем сервере не воспроизвести.
    result = await gateway._call("CreateRoom", flaky)

    assert (result, attempts) == ("ok", 3)
