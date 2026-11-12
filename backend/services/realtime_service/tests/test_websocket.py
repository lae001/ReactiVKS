"""Проверка vks.v1 через WebSocket и события шины."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from realtime_service.api.websocket import router
from realtime_service.consumers.events import route_event
from realtime_service.domain.meeting import MeetingSnapshot, ParticipantSnapshot
from realtime_service.services.live_rooms import LiveRooms
from vks_common.clock import FixedClock
from vks_common.testing import TokenFactory
from vks_contracts import EventPayload
from vks_contracts.envelope import envelope_for
from vks_contracts.meeting_events import ConsentChanged
from vks_contracts.ml_events import EmotionProbabilities, EmotionSample, MlStatus
from vks_contracts.report_events import ReportReady


@dataclass
class Panel:
    client: TestClient
    clock: FixedClock
    rooms: LiveRooms
    tokens: TokenFactory
    organizer_id: UUID
    meeting_id: UUID
    participant_id: UUID

    def authenticate(self, socket: WebSocketTestSession) -> None:
        socket.send_json({"type": "auth", "token": self.tokens.issue(user_id=self.organizer_id), "id": "auth"})
        response = socket.receive_json()
        assert response["type"] == "welcome"
        assert response["id"] == "auth"

    def emit(self, socket: WebSocketTestSession, event: EventPayload) -> None:
        value = (
            envelope_for(event, event_id=uuid4(), occurred_at=self.clock.now(), producer="test")
            .model_dump_json()
            .encode()
        )
        socket.portal.call(lambda: route_event(self.rooms, key=event.key().encode(), value=value))

    async def is_allowed(self, meeting_id: UUID, user_id: UUID) -> bool:
        return meeting_id == self.meeting_id and user_id == self.organizer_id

    async def snapshot(self, meeting_id: UUID) -> MeetingSnapshot:
        return MeetingSnapshot(
            owner_id=self.organizer_id,
            is_analyzed=True,
            is_closed=False,
            participants=(
                ParticipantSnapshot(
                    self.participant_id, "Гость", "guest", True, True, False, self.clock.now(), self.clock.now()
                ),
            ),
        )


@pytest.fixture
def panel() -> Panel:
    app = FastAPI()
    app.include_router(router)
    clock = FixedClock(datetime.now(UTC))
    rooms = LiveRooms()
    tokens = TokenFactory()
    result = Panel(TestClient(app), clock, rooms, tokens, uuid4(), uuid4(), uuid4())
    app.state.clock = clock
    app.state.rooms = rooms
    app.state.token_verifier = tokens.verifier()
    app.state.meetings = result
    return result


def test_subscribed_owner_receives_emotions_and_loses_them_on_revoke(panel: Panel) -> None:
    with panel.client.websocket_connect("/ws", subprotocols=["vks.v1"]) as socket:
        panel.authenticate(socket)
        socket.send_json({"type": "subscribe", "meeting_id": str(panel.meeting_id), "id": 7})
        snapshot = socket.receive_json()
        assert snapshot["type"] == "subscribed"
        assert snapshot["id"] == 7
        assert snapshot["snapshot"]["participants"][0]["state"] == "camera_off"

        panel.emit(
            socket,
            MlStatus(meeting_id=panel.meeting_id, state="active", effective_fps=3, target_fps=3, worker_id="worker"),
        )
        assert socket.receive_json()["state"] == "active"
        sample = EmotionSample(
            meeting_id=panel.meeting_id,
            participant_id=panel.participant_id,
            ts=panel.clock.now(),
            state="analyzing",
            probs=EmotionProbabilities(angry=0, disgust=0, fear=0, happy=1, sad=0, surprise=0, neutral=0),
            dominant="happy",
            confidence=1,
            model_version="test",
        )
        panel.emit(socket, sample)
        batch = socket.receive_json()
        assert batch["type"] == "emotion.update"
        assert batch["items"][0]["p"] == [0, 0, 0, 1, 0, 0, 0]

        panel.emit(
            socket,
            ConsentChanged(
                meeting_id=panel.meeting_id,
                participant_id=panel.participant_id,
                consent_state="revoked",
                notice_version="test",
                decided_at=panel.clock.now(),
            ),
        )
        assert socket.receive_json()["state"] == "no_consent"
        panel.emit(socket, sample)
        socket.send_json({"type": "subscribe", "meeting_id": str(panel.meeting_id)})
        assert socket.receive_json()["snapshot"]["participants"][0]["last"] is None
        socket.portal.call(panel.clock.advance, timedelta(seconds=11))
        assert socket.receive_json()["state"] == "unavailable"
        panel.emit(socket, ReportReady(meeting_id=panel.meeting_id, owner_id=panel.organizer_id))
        assert socket.receive_json()["type"] == "report.ready"


def test_refuses_foreign_meeting(panel: Panel) -> None:
    with panel.client.websocket_connect("/ws", subprotocols=["vks.v1"]) as socket:
        panel.authenticate(socket)

        socket.send_json({"type": "subscribe", "meeting_id": str(uuid4()), "id": "foreign"})

        assert socket.receive_json()["id"] == "foreign"
        with pytest.raises(WebSocketDisconnect) as raised:
            socket.receive_json()
        assert raised.value.code == 4403


def test_refuses_identity_change_on_refresh(panel: Panel) -> None:
    with panel.client.websocket_connect("/ws", subprotocols=["vks.v1"]) as socket:
        panel.authenticate(socket)
        socket.send_json({"type": "auth.refresh", "token": panel.tokens.issue(user_id=panel.organizer_id)})
        assert socket.receive_json()["type"] == "welcome"

        socket.send_json({"type": "auth.refresh", "token": panel.tokens.issue(user_id=uuid4())})

        assert socket.receive_json()["code"] == "forbidden"
        with pytest.raises(WebSocketDisconnect) as raised:
            socket.receive_json()
        assert raised.value.code == 4403


def test_requires_subscription_before_deadline(panel: Panel) -> None:
    with panel.client.websocket_connect("/ws", subprotocols=["vks.v1"]) as socket:
        panel.authenticate(socket)

        socket.portal.call(panel.clock.advance, timedelta(seconds=10))

        with pytest.raises(WebSocketDisconnect) as raised:
            socket.receive_json()
        assert raised.value.code == 4408
