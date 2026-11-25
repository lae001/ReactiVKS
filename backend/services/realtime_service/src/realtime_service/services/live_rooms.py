"""Текущее состояние комнат с подписчиками и маршрутизация событий Kafka."""

from asyncio import Queue, QueueFull
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from realtime_service.domain.meeting import MeetingSnapshot, ParticipantRole
from vks_contracts import ParsedEvent
from vks_contracts.meeting_events import (
    ConsentChanged,
    MeetingCancelled,
    MeetingDeleted,
    MeetingEnded,
    MeetingStarted,
    ParticipantJoined,
    ParticipantLeft,
    ParticipantRegistered,
)
from vks_contracts.ml_events import EMOTIONS, EmotionSample, MlStatus
from vks_contracts.report_events import ReportReady

type Message = dict[str, object]


@dataclass(eq=False, slots=True)
class Subscription:
    output: Queue[Message]
    delivered: dict[UUID, EmotionSample] = field(default_factory=dict)
    analysis: Message = field(default_factory=dict)
    close_code: int | None = None

    def notify(self, message: Message) -> None:
        try:
            self.output.put_nowait(message)
        except QueueFull:
            self.close_code = 1013


@dataclass(slots=True)
class LiveParticipant:
    display_name: str
    role: ParticipantRole
    has_consent: bool
    is_online: bool
    last: EmotionSample | None = None
    consent_at: datetime | None = None
    presence_at: datetime | None = None
    is_removed: bool = False

    @property
    def state(self) -> str:
        if not self.is_online:
            return "left"
        if not self.has_consent:
            return "no_consent"
        return self.last.state if self.last is not None else "camera_off"


class LiveRoom:
    def __init__(self, meeting_id: UUID) -> None:
        self.id = meeting_id
        self.owner_id: UUID | None = None
        self.is_analyzed = False
        self.is_closed = False
        self.is_deleted = False
        self.participants: dict[UUID, LiveParticipant] = {}
        self.subscriptions: set[Subscription] = set()
        self.reservations = 0
        self._bootstrap: deque[ParsedEvent] = deque(maxlen=2048)
        self._heartbeat: tuple[datetime, MlStatus] | None = None

    def initialize(self, snapshot: MeetingSnapshot) -> None:
        if self.owner_id is not None:
            return
        self.owner_id = snapshot.owner_id
        self.is_analyzed = snapshot.is_analyzed
        self.is_closed = snapshot.is_closed
        self.participants = {
            participant.id: LiveParticipant(
                display_name=participant.display_name,
                role=participant.role,
                has_consent=participant.has_consent,
                is_online=participant.is_online and not snapshot.is_closed,
                consent_at=participant.updated_at,
                presence_at=participant.presence_at,
                is_removed=participant.is_removed,
            )
            for participant in snapshot.participants
        }
        while self._bootstrap:
            self.apply(self._bootstrap.popleft())

    def analysis(self, now: datetime) -> Message:
        if not self.is_analyzed:
            return {"state": "off"}
        if self._heartbeat is not None:
            timestamp, status = self._heartbeat
            if status.state != "stopped" and now - timestamp <= timedelta(seconds=10):
                return {"state": status.state, "effective_fps": status.effective_fps}
        return {"state": "unavailable"}

    def snapshot(self, now: datetime) -> Message:
        return {
            "analysis": self.analysis(now),
            "labels": list(EMOTIONS),
            "participants": [
                {
                    "participant_id": str(participant_id),
                    "display_name": participant.display_name,
                    "role": participant.role,
                    "state": participant.state,
                    "last": _sample_fields(participant.last) if participant.last is not None else None,
                }
                for participant_id, participant in self.participants.items()
            ],
        }

    def batch(self, subscription: Subscription) -> Message | None:
        items = []
        for participant_id, participant in self.participants.items():
            sample = participant.last
            if sample is not None and subscription.delivered.get(participant_id) is not sample:
                subscription.delivered[participant_id] = sample
                items.append({"participant_id": str(participant_id), "state": sample.state, **_sample_fields(sample)})
        return self.message("emotion.update", items=items) if items else None

    def apply(self, event: ParsedEvent) -> None:
        if self.owner_id is None:
            self._bootstrap.append(event)
            return
        payload = event.payload
        if isinstance(payload, EmotionSample):
            self._record_sample(payload)
        elif isinstance(payload, MlStatus):
            timestamp = event.envelope.occurred_at
            if self._heartbeat is None or timestamp >= self._heartbeat[0]:
                self._heartbeat = (timestamp, payload)
        elif isinstance(payload, MeetingStarted) and not self.is_closed:
            self.is_analyzed = payload.analysis_enabled
        elif isinstance(payload, (MeetingEnded, MeetingCancelled, MeetingDeleted)):
            self.is_closed = True
            self.is_analyzed = False
            self._heartbeat = None
            for participant in self.participants.values():
                participant.last = None
                participant.is_online = False
            if isinstance(payload, MeetingDeleted):
                self.is_deleted = True
                for subscription in self.subscriptions:
                    subscription.close_code = 4403
            elif isinstance(payload, MeetingEnded):
                self._notify(self.message("meeting.ended"))
        elif isinstance(payload, ReportReady):
            if payload.owner_id == self.owner_id:
                self._notify(self.message("report.ready"))
        elif isinstance(payload, ParticipantRegistered):
            self.participants.setdefault(
                payload.participant_id,
                LiveParticipant(payload.display_name, payload.role, payload.consent_state == "granted", False),
            )
        elif not self.is_closed and isinstance(payload, (ParticipantJoined, ParticipantLeft, ConsentChanged)):
            self._update_participant(payload)

    def message(self, kind: str, **fields: object) -> Message:
        return {"type": kind, "meeting_id": str(self.id), **fields}

    def _record_sample(self, sample: EmotionSample) -> None:
        participant = self.participants.get(sample.participant_id)
        if participant is None or not self.is_analyzed or not participant.has_consent or not participant.is_online:
            return
        if any(at is not None and sample.ts < at for at in (participant.consent_at, participant.presence_at)):
            return
        if participant.last is None or sample.ts >= participant.last.ts:
            participant.last = sample

    def _update_participant(self, event: ParticipantJoined | ParticipantLeft | ConsentChanged) -> None:
        participant = self.participants.get(event.participant_id)
        if participant is None:
            return
        if isinstance(event, ConsentChanged):
            if participant.consent_at is not None and event.decided_at < participant.consent_at:
                return
            participant.has_consent = event.consent_state == "granted"
            participant.consent_at = event.decided_at
        else:
            joined = isinstance(event, ParticipantJoined)
            at = event.joined_at if isinstance(event, ParticipantJoined) else event.left_at
            if participant.is_removed or (participant.presence_at is not None and at < participant.presence_at):
                return
            participant.is_online = joined
            participant.presence_at = at
            if isinstance(event, ParticipantLeft) and event.reason == "removed":
                participant.is_removed = True
        participant.last = None
        self._notify(
            self.message(
                "participant.status",
                participant_id=str(event.participant_id),
                display_name=participant.display_name,
                state=participant.state,
            )
        )

    def _notify(self, message: Message) -> None:
        for subscription in self.subscriptions:
            subscription.notify(message)


class LiveRooms:
    def __init__(self) -> None:
        self._rooms: dict[UUID, LiveRoom] = {}

    def reserve(self, meeting_id: UUID) -> LiveRoom:
        room = self._rooms.get(meeting_id)
        if room is None:
            room = self._rooms[meeting_id] = LiveRoom(meeting_id)
        room.reservations += 1
        return room

    def release(self, room: LiveRoom) -> None:
        room.reservations -= 1
        self.prune(room)

    def prune(self, room: LiveRoom) -> None:
        if room.reservations == 0 and not room.subscriptions:
            del self._rooms[room.id]

    def tracked(self, meeting_id: UUID) -> LiveRoom | None:
        return self._rooms.get(meeting_id)


def _sample_fields(sample: EmotionSample) -> Message:
    fields: Message = {"ts": sample.ts.isoformat()}
    if sample.probs is not None:
        probabilities = sample.probs.model_dump()
        fields.update(
            dominant=sample.dominant, confidence=sample.confidence, p=[probabilities[label] for label in EMOTIONS]
        )
    return fields
