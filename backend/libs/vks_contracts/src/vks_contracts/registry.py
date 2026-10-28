"""Реестр типов событий и разбор сообщения потребителем."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from vks_contracts.envelope import EventEnvelope, EventPayload
from vks_contracts.meeting_events import (
    ConsentChanged,
    MeetingCancelled,
    MeetingCreated,
    MeetingDeleted,
    MeetingEnded,
    MeetingStarted,
    MeetingUpdated,
    ParticipantJoined,
    ParticipantLeft,
    ParticipantRegistered,
)
from vks_contracts.ml_events import EmotionSample, MlStatus
from vks_contracts.report_events import ReportFailed, ReportReady
from vks_contracts.user_events import UserBlocked, UserDeleted, UserUnblocked

__all__ = ["EVENT_TYPES", "IncompatibleEvent", "ParsedEvent", "UnknownEvent", "parse_event"]

_PAYLOADS: tuple[type[EventPayload], ...] = (
    MeetingCreated,
    MeetingUpdated,
    MeetingStarted,
    MeetingEnded,
    MeetingCancelled,
    MeetingDeleted,
    ParticipantRegistered,
    ParticipantJoined,
    ParticipantLeft,
    ConsentChanged,
    UserBlocked,
    UserUnblocked,
    UserDeleted,
    ReportReady,
    ReportFailed,
    MlStatus,
    EmotionSample,
)

# (тип, версия) → модель payload. Явный список, а не регистрация по импорту: читатель видит все типы здесь.
EVENT_TYPES: dict[tuple[str, int], type[EventPayload]] = {
    (payload.event_type, payload.event_version): payload for payload in _PAYLOADS
}


class UnknownEvent(ValueError):
    """Тип или версия, которых этот потребитель не знает: журнал ``warning`` и пропуск (tolerant reader)."""


class IncompatibleEvent(ValueError):
    """Сообщение не соответствует контракту – постоянная ошибка, место ему в ``<топик>.dlq``."""


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    envelope: EventEnvelope
    payload: EventPayload


def parse_event(value: bytes | str) -> ParsedEvent:
    """Разобрать значение сообщения Kafka: конверт, затем payload по его типу и версии."""
    try:
        envelope = EventEnvelope.model_validate_json(value)
    except ValidationError as error:
        raise IncompatibleEvent(f"envelope does not match the contract: {error.error_count()} errors") from error
    model = EVENT_TYPES.get((envelope.type, envelope.version))
    if model is None:
        raise UnknownEvent(f"unknown event {envelope.type} v{envelope.version}")
    try:
        payload = model.model_validate(envelope.payload)
    except ValidationError as error:
        raise IncompatibleEvent(f"payload of {envelope.type} does not match the contract") from error
    return ParsedEvent(envelope=envelope, payload=payload)
