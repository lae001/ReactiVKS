"""Конверт события и базовый класс payload (events.md, «Формат сообщения»)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from vks_contracts.topics import Topic

__all__ = ["EventEnvelope", "EventPayload", "envelope_for", "kafka_headers"]


class EventPayload(BaseModel):
    """Payload события. Наследник объявляет тип, версию, топик и ключ упорядочивания.

    Неизвестные поля игнорируются: добавление необязательного поля – не новая версия (правила эволюции).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_type: ClassVar[str]
    event_version: ClassVar[int] = 1
    topic: ClassVar[Topic]

    def key(self) -> str:
        """Ключ сообщения: события одного агрегата обрабатываются по порядку."""
        raise NotImplementedError


class MeetingKeyed(EventPayload):
    """События встречи и ее участников – ключ ``meeting_id``."""

    meeting_id: UUID

    def key(self) -> str:
        return str(self.meeting_id)


class UserKeyed(EventPayload):
    """События учетной записи – ключ ``user_id``."""

    user_id: UUID

    def key(self) -> str:
        return str(self.user_id)


class EventEnvelope(BaseModel):
    """Значение сообщения Kafka: метаданные и payload.

    ``payload`` в конверте – словарь: модель payload выбирается по ``type`` и ``version`` (:func:`parse_event`).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_id: UUID = Field(description="UUIDv7 – для идемпотентной обработки")
    type: str
    version: int = Field(ge=1)
    occurred_at: AwareDatetime
    producer: str = Field(min_length=1, examples=["meeting-service"])
    correlation_id: str | None = Field(default=None, description="request_id исходного запроса")
    payload: dict[str, object]


def envelope_for(
    payload: EventPayload,
    *,
    event_id: UUID,
    occurred_at: datetime,
    producer: str,
    correlation_id: str | None = None,
) -> EventEnvelope:
    """Конверт события. Идентификатор и время приносит производитель: контракты не знают ни часов, ни генератора."""
    return EventEnvelope(
        event_id=event_id,
        type=payload.event_type,
        version=payload.event_version,
        occurred_at=occurred_at,
        producer=producer,
        correlation_id=correlation_id,
        payload=payload.model_dump(mode="json"),
    )


def kafka_headers(envelope: EventEnvelope) -> list[tuple[str, bytes]]:
    """Заголовки сообщения дублируют поля конверта: потребитель фильтрует, не разбирая тело."""
    headers = [
        ("event_type", envelope.type),
        ("event_id", str(envelope.event_id)),
        ("event_version", str(envelope.version)),
        ("producer", envelope.producer),
    ]
    if envelope.correlation_id is not None:
        headers.append(("correlation_id", envelope.correlation_id))
    return [(name, value.encode("utf-8")) for name, value in headers]
