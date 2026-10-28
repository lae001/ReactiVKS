"""Контракты событий Kafka (docs/api/events.md): конверт, payload каждого типа, топики и ключи.

Производитель строит событие моделью payload и :func:`envelope_for`; потребитель разбирает сообщение
:func:`parse_event` и получает ту же модель. Неизвестные поля игнорируются (tolerant reader), неизвестный тип –
:class:`UnknownEvent`, который потребитель журналирует и пропускает.
"""

from vks_contracts.envelope import EventEnvelope, EventPayload, envelope_for, kafka_headers
from vks_contracts.registry import EVENT_TYPES, IncompatibleEvent, ParsedEvent, UnknownEvent, parse_event
from vks_contracts.topics import Topic

__all__ = [
    "EVENT_TYPES",
    "EventEnvelope",
    "EventPayload",
    "IncompatibleEvent",
    "ParsedEvent",
    "Topic",
    "UnknownEvent",
    "envelope_for",
    "kafka_headers",
    "parse_event",
]
