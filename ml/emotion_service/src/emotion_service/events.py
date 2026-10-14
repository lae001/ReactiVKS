"""События emotion.samples и ml.status в формате docs/api/events.md.

Временная копия контракта: после появления backend/libs/vks_contracts (EMO-50) модели заменяются импортом оттуда.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from emotion_service.attention import Attention
from emotion_service.pipeline import FaceResult

PRODUCER = "emotion-ml-service"
SampleState = Literal["analyzing", "no_face", "camera_off", "no_consent"]
MlState = Literal["active", "degraded", "stopped"]


def uuid7() -> str:
    """UUIDv7 (RFC 9562): 48 бит миллисекунд Unix-времени + случайные биты – сортируется по времени."""
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(os.urandom(10), "big")
    value = (value & ~(0xF << 76)) | (0x7 << 76)  # версия
    value = (value & ~(0x3 << 62)) | (0x2 << 62)  # вариант RFC
    return str(uuid.UUID(int=value))


def iso_now(at: datetime | None = None) -> str:
    moment = (at or datetime.now(UTC)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def envelope(event_type: str, payload: dict[str, Any], correlation_id: str | None = None) -> dict[str, Any]:
    return {
        "event_id": uuid7(),
        "type": event_type,
        "version": 1,
        "occurred_at": iso_now(),
        "producer": PRODUCER,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def emotion_sample(
    meeting_id: str,
    participant_id: str,
    received_at: datetime,
    model_version: str,
    result: FaceResult | None = None,
    state: SampleState | None = None,
) -> dict[str, Any]:
    """Payload emotion.sample: из результата конвейера или для состояния без анализа (camera_off, no_consent).

    attention – необязательное поле (добавлено без смены version): внимание участника по позе головы.
    """
    actual_state: SampleState = result.state if result is not None else (state or "no_face")
    analyzing = result is not None and actual_state == "analyzing"
    return {
        "meeting_id": meeting_id,
        "participant_id": participant_id,
        "ts": iso_now(received_at),
        "state": actual_state,
        "probs": result.probs if analyzing and result else None,
        "raw_dominant": result.raw_dominant if analyzing and result else None,
        "dominant": result.dominant if analyzing and result else None,
        "confidence": result.confidence if analyzing and result else None,
        "face_box_area": result.face_box_area if analyzing and result else None,
        "model_version": model_version,
        "attention": attention_payload(result.attention) if result is not None and result.attention else None,
    }


def attention_payload(attention: Attention) -> dict[str, Any]:
    pose = attention.pose
    return {
        "state": attention.state,
        "interest": attention.interest,
        "looking": attention.looking,
        "yaw_deg": round(pose.yaw_deg, 1) if pose else None,
        "pitch_deg": round(pose.pitch_deg, 1) if pose and pose.pitch_deg is not None else None,
        "gaze_x": round(pose.gaze_x, 2) if pose and pose.gaze_x is not None else None,
        "source": pose.source if pose else None,
    }


def ml_status(
    meeting_id: str, state: MlState, effective_fps: float, target_fps: float, worker_id: str, reason: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "meeting_id": meeting_id,
        "state": state,
        "effective_fps": round(effective_fps, 2),
        "target_fps": target_fps,
        "worker_id": worker_id,
    }
    if reason:
        payload["reason"] = reason
    return payload


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
