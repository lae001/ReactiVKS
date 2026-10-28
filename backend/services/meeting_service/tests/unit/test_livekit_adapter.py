import base64
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import aiohttp
import jwt
import pytest
from google.protobuf.json_format import MessageToJson
from livekit import api
from livekit.protocol.models import DisconnectReason, ParticipantInfo, Room
from livekit.protocol.webhook import WebhookEvent

from meeting_service.adapters.livekit_server import LiveKitServerGateway
from meeting_service.adapters.livekit_webhooks import LiveKitWebhookVerifier
from meeting_service.domain.errors import LiveKitUnavailable, WebhookRejected
from meeting_service.domain.livekit import LeaveReason, MediaKind, RoomAccess, RoomEventKind

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


async def test_moderation_reports_unreachable_livekit(gateway: LiveKitServerGateway) -> None:
    with pytest.raises(LiveKitUnavailable):
        await gateway.mute("0192-room", "p_0192", MediaKind.AUDIO)
    with pytest.raises(LiveKitUnavailable):
        await gateway.remove("0192-room", "p_0192")


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


def signed(body: str, secret: str = API_SECRET) -> str:
    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    return api.AccessToken(API_KEY, secret).with_sha256(digest).to_jwt()


def webhook_body(event: str, **participant: object) -> str:
    message = WebhookEvent(event=event, id="EV_1", created_at=1795158000, room=Room(name="0192-room"))
    if participant:
        message.participant.CopyFrom(ParticipantInfo(**participant))  # type: ignore[arg-type]  # поля по имени
    return MessageToJson(message)


def test_webhook_signed_with_api_key_is_parsed() -> None:
    verifier = LiveKitWebhookVerifier(api_key=API_KEY, api_secret=API_SECRET)
    body = webhook_body("participant_left", identity="p_0192", disconnect_reason=DisconnectReason.PARTICIPANT_REMOVED)

    event = verifier.parse(body, signed(body))

    assert (event.event_id, event.kind, event.room, event.identity) == (
        "EV_1",
        RoomEventKind.PARTICIPANT_LEFT,
        "0192-room",
        "p_0192",
    )
    assert event.occurred_at == datetime.fromtimestamp(1795158000, tz=UTC)
    assert event.leave_reason is LeaveReason.REMOVED
    assert event.is_agent is False


def test_agent_and_unknown_events_are_recognized() -> None:
    verifier = LiveKitWebhookVerifier(api_key=API_KEY, api_secret=API_SECRET)
    agent = webhook_body("participant_joined", identity="agent-1", kind=ParticipantInfo.Kind.AGENT)
    track = webhook_body("track_published")

    assert verifier.parse(agent, signed(agent)).is_agent is True
    assert verifier.parse(track, signed(track)).kind is RoomEventKind.OTHER


@pytest.mark.parametrize(
    "authorization",
    [
        pytest.param("", id="missing"),
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(signed("{}"), id="other-body"),
        pytest.param(signed(webhook_body("room_finished"), secret="other-secret-0123456789abcdef01234"), id="key"),
    ],
)
def test_webhook_without_valid_signature_is_rejected(authorization: str) -> None:
    verifier = LiveKitWebhookVerifier(api_key=API_KEY, api_secret=API_SECRET)

    with pytest.raises(WebhookRejected):
        verifier.parse(webhook_body("room_finished"), authorization)
