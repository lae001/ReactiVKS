"""События emotion.samples и ml.status – модели backend/libs/vks_contracts (единственный источник правды формата).

Payload собирается здесь и проходит валидацию контракта (диапазоны, «вероятности есть ровно при analyzing») до
отправки: сервис не может опубликовать событие, которое потребитель отвергнет.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Literal

from vks_contracts.envelope import EventEnvelope, EventPayload, envelope_for
from vks_contracts.ml_events import Attention as AttentionModel
from vks_contracts.ml_events import EmotionProbabilities, EmotionSample, MlStatus

from emotion_service.attention import Attention
from emotion_service.pipeline import FaceResult

PRODUCER = "emotion-ml-service"
SampleState = Literal["analyzing", "no_face", "camera_off", "no_consent"]
MlState = Literal["active", "degraded", "stopped"]


def uuid7() -> uuid.UUID:
    """UUIDv7 (RFC 9562): 48 бит миллисекунд Unix-времени + случайные биты – сортируется по времени."""
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(os.urandom(10), "big")
    value = (value & ~(0xF << 76)) | (0x7 << 76)  # версия
    value = (value & ~(0x3 << 62)) | (0x2 << 62)  # вариант RFC
    return uuid.UUID(int=value)


def iso_now(at: datetime | None = None) -> str:
    moment = (at or datetime.now(UTC)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def envelope(payload: EventPayload, correlation_id: str | None = None) -> EventEnvelope:
    return envelope_for(
        payload, event_id=uuid7(), occurred_at=datetime.now(UTC), producer=PRODUCER, correlation_id=correlation_id
    )


def attention_model(attention: Attention) -> AttentionModel:
    pose = attention.pose
    return AttentionModel(
        state=attention.state,
        interest=attention.interest,
        looking=attention.looking,
        yaw_deg=round(pose.yaw_deg, 1) if pose else None,
        pitch_deg=round(pose.pitch_deg, 1) if pose and pose.pitch_deg is not None else None,
        gaze_x=round(pose.gaze_x, 2) if pose and pose.gaze_x is not None else None,
        source=pose.source if pose else None,
    )


def attention_payload(attention: Attention) -> dict[str, object]:
    """Внимание словарем – для страницы демонстрации; в событии – vks_contracts.ml_events.Attention."""
    return attention_model(attention).model_dump(mode="json")


def emotion_sample(
    meeting_id: str,
    participant_id: str,
    received_at: datetime,
    model_version: str,
    result: FaceResult | None = None,
    state: SampleState | None = None,
) -> EmotionSample:
    """Отсчет по участнику: из результата конвейера или для состояния без анализа (camera_off, no_consent)."""
    actual_state: SampleState = result.state if result is not None else (state or "no_face")
    analyzing = result is not None and actual_state == "analyzing" and result.probs is not None
    return EmotionSample(
        meeting_id=uuid.UUID(meeting_id),
        participant_id=uuid.UUID(participant_id),
        ts=received_at,
        state=actual_state,
        probs=EmotionProbabilities(**result.probs) if analyzing and result and result.probs else None,
        raw_dominant=result.raw_dominant if analyzing and result else None,  # type: ignore[arg-type]
        dominant=result.dominant if analyzing and result else None,  # type: ignore[arg-type]
        confidence=result.confidence if analyzing and result else None,
        face_box_area=result.face_box_area if analyzing and result else None,
        model_version=model_version,
        attention=attention_model(result.attention) if result is not None and result.attention else None,
    )


def ml_status(
    meeting_id: str, state: MlState, effective_fps: float, target_fps: float, worker_id: str, reason: str | None = None
) -> MlStatus:
    return MlStatus(
        meeting_id=uuid.UUID(meeting_id),
        state=state,
        effective_fps=round(max(effective_fps, 0.0), 2),
        target_fps=round(target_fps),
        worker_id=worker_id,
        reason=reason,
    )


class StateThrottle:
    """Правило экономии трафика: no_consent и camera_off – только при смене состояния, no_face – не чаще 1 раза в с."""

    def __init__(self, no_face_interval_s: float = 1.0) -> None:
        self.no_face_interval_s = no_face_interval_s
        self._last_state: dict[str, str] = {}
        self._last_no_face: dict[str, float] = {}

    def should_publish(self, participant_id: str, state: str, now: float) -> bool:
        previous = self._last_state.get(participant_id)
        self._last_state[participant_id] = state
        if state == "analyzing":
            return True
        if state in ("no_consent", "camera_off"):
            return previous != state
        last = self._last_no_face.get(participant_id)
        if previous != state or last is None or now - last >= self.no_face_interval_s:
            self._last_no_face[participant_id] = now
            return True
        return False

    def forget(self, participant_id: str) -> None:
        self._last_state.pop(participant_id, None)
        self._last_no_face.pop(participant_id, None)
