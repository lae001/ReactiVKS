"""Контрактные тесты событий (conventions.md, §13): схема совпадает со снимком, примеры из events.md разбираются."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from vks_contracts import (
    EVENT_TYPES,
    EventPayload,
    IncompatibleEvent,
    Topic,
    UnknownEvent,
    envelope_for,
    kafka_headers,
    parse_event,
)
from vks_contracts.meeting_events import MeetingEnded, MeetingStarted, ParticipantRegistered
from vks_contracts.ml_events import EmotionSample
from vks_contracts.schema import render
from vks_contracts.user_events import UserBlocked

SNAPSHOT = Path(__file__).parent / "snapshots" / "events.schema.json"
TOPICS_YAML = Path(__file__).resolve().parents[4] / "deploy" / "kafka" / "topics.yaml"
EVENTS_MD = Path(__file__).resolve().parents[4] / "docs" / "api" / "events.md"

NOW = datetime(2026, 11, 20, 7, 5, 11, tzinfo=UTC)
MEETING_ID = UUID("0192f1c4-0000-7000-8000-000000000001")
PARTICIPANT_ID = UUID("0192f1c4-0000-7000-8000-000000000002")


def message(event: EventPayload, **overrides: object) -> bytes:
    """Значение сообщения Kafka; ``overrides`` заменяют поля конверта – чтобы испортить его для теста."""
    built = envelope_for(event, event_id=uuid4(), occurred_at=NOW, producer="meeting-service")
    return json.dumps(built.model_dump(mode="json") | overrides).encode()


def test_schema_matches_snapshot() -> None:
    """Изменился контракт – обновите снимок (make contracts-snapshot) и docs/api/events.md в том же изменении."""
    assert render() == SNAPSHOT.read_text(encoding="utf-8")


def documented_event_types() -> set[str]:
    """Первый столбец таблиц «| type | payload |» из events.md."""
    types: set[str] = set()
    in_table = False
    for line in EVENTS_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("| type |"):
            in_table = True
        elif not line.startswith("|"):
            in_table = False
        elif in_table and (found := re.match(r"^\| `([a-z_]+\.[a-z_]+)` \|", line)):
            types.add(found.group(1))
    return types


def test_every_event_type_of_events_md_has_a_model() -> None:
    assert documented_event_types() == {event_type for event_type, _ in EVENT_TYPES}


def test_every_topic_and_its_dead_letters_are_created_by_kafka_init() -> None:
    created = set(re.findall(r"- name: (\S+)", TOPICS_YAML.read_text(encoding="utf-8")))

    for topic in Topic:
        assert {topic.value, topic.dead_letters} <= created


def test_event_survives_producer_and_consumer() -> None:
    started = MeetingStarted(
        meeting_id=MEETING_ID,
        owner_id=uuid4(),
        title="Планерка",
        started_at=NOW,
        analysis_enabled=True,
        analysis_fps=3,
    )

    parsed = parse_event(message(started))

    assert parsed.payload == started
    assert parsed.envelope.type == "meeting.started"
    assert parsed.envelope.version == 1


def test_key_orders_events_of_one_aggregate() -> None:
    assert MeetingEnded(meeting_id=MEETING_ID, ended_at=NOW, reason="organizer").key() == str(MEETING_ID)
    user_id = uuid4()
    assert UserBlocked(user_id=user_id).key() == str(user_id)


def test_headers_duplicate_the_envelope() -> None:
    envelope = envelope_for(
        UserBlocked(user_id=uuid4()), event_id=uuid4(), occurred_at=NOW, producer="auth-service", correlation_id="c0a8"
    )

    headers = dict(kafka_headers(envelope))

    assert headers == {
        "event_type": b"user.blocked",
        "event_id": str(envelope.event_id).encode(),
        "event_version": b"1",
        "producer": b"auth-service",
        "correlation_id": b"c0a8",
    }


def test_unknown_fields_are_ignored() -> None:
    """Tolerant reader: новое необязательное поле производителя не ломает старого потребителя."""
    raw = json.loads(message(MeetingEnded(meeting_id=MEETING_ID, ended_at=NOW, reason="admin")))
    raw["payload"]["added_later"] = 42
    raw["schema_hint"] = "x"

    parsed = parse_event(json.dumps(raw))

    assert parsed.payload == MeetingEnded(meeting_id=MEETING_ID, ended_at=NOW, reason="admin")


@pytest.mark.parametrize(("event_type", "version"), [("meeting.archived", 1), ("meeting.started", 2)])
def test_unknown_type_or_version_is_skipped(event_type: str, version: int) -> None:
    raw = message(MeetingEnded(meeting_id=MEETING_ID, ended_at=NOW, reason="admin"), type=event_type, version=version)

    with pytest.raises(UnknownEvent):
        parse_event(raw)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"not json", id="not-json"),
        pytest.param(b'{"type": "meeting.ended"}', id="no-envelope-fields"),
        pytest.param(
            message(MeetingEnded(meeting_id=MEETING_ID, ended_at=NOW, reason="admin"), payload={"meeting_id": "x"}),
            id="broken-payload",
        ),
    ],
)
def test_message_that_breaks_the_contract_is_incompatible(raw: bytes) -> None:
    with pytest.raises(IncompatibleEvent):
        parse_event(raw)


def test_emotion_sample_from_events_md() -> None:
    sample = EmotionSample.model_validate(
        {
            "meeting_id": str(MEETING_ID),
            "participant_id": str(PARTICIPANT_ID),
            "ts": "2026-11-20T07:12:03.643Z",
            "state": "analyzing",
            "probs": {
                "angry": 0.03,
                "disgust": 0.01,
                "fear": 0.02,
                "happy": 0.21,
                "sad": 0.07,
                "surprise": 0.08,
                "neutral": 0.58,
            },
            "raw_dominant": "neutral",
            "dominant": "neutral",
            "confidence": 0.58,
            "face_box_area": 0.12,
            "model_version": "emotion-effnetb0@1.0.0",
        }
    )

    assert sample.dominant == "neutral"
    assert sample.topic is Topic.EMOTION_SAMPLES


@pytest.mark.parametrize(
    ("state", "probs"),
    [
        pytest.param("analyzing", None, id="analyzing-without-probs"),
        pytest.param(
            "no_face",
            {"angry": 0, "disgust": 0, "fear": 0, "happy": 1, "sad": 0, "surprise": 0, "neutral": 0},
            id="probs-without-face",
        ),
    ],
)
def test_probabilities_exist_only_while_analyzing(state: str, probs: object) -> None:
    with pytest.raises(ValidationError, match="probs"):
        EmotionSample.model_validate(
            {
                "meeting_id": str(MEETING_ID),
                "participant_id": str(PARTICIPANT_ID),
                "ts": "2026-11-20T07:12:03Z",
                "state": state,
                "probs": probs,
                "model_version": "emotion-effnetb0@1.0.0",
            }
        )


def test_unknown_role_is_refused() -> None:
    with pytest.raises(ValidationError, match="role"):
        ParticipantRegistered(
            meeting_id=MEETING_ID,
            participant_id=PARTICIPANT_ID,
            display_name="Анна",
            role="host",
            consent_state="granted",
        )


def test_naive_time_is_refused() -> None:
    with pytest.raises(ValidationError, match="ended_at"):
        MeetingEnded.model_validate(
            {"meeting_id": str(MEETING_ID), "ended_at": "2026-11-20T07:00:00", "reason": "admin"}
        )
