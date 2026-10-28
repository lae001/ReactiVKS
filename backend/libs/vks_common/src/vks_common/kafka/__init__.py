"""События Kafka (ADR-012, conventions.md, §6–7): публикация через transactional outbox и потребление.

- :class:`EventProducer` – идемпотентный производитель (``acks=all``).
- :func:`outbox_table`, :class:`OutboxWriter`, :class:`OutboxRelay` – событие пишется в таблицу ``outbox`` в той же
  транзакции, что и изменение данных, а фоновая задача отправляет его в Kafka.
- :class:`EventConsumer` – потребитель с ручной фиксацией смещений после обработки и DLQ.
- :func:`run_outbox_relay` – фоновая задача ``lifespan``: подключение к брокеру с повторами и работа релея.
"""

from vks_common.kafka.background import log_unexpected_stop, run_outbox_relay
from vks_common.kafka.consumer import EventConsumer, EventHandler
from vks_common.kafka.outbox import OUTBOX_NOTIFY, OutboxRelay, OutboxWriter, outbox_table
from vks_common.kafka.producer import EventProducer, OutgoingMessage

__all__ = [
    "OUTBOX_NOTIFY",
    "EventConsumer",
    "EventHandler",
    "EventProducer",
    "OutboxRelay",
    "OutboxWriter",
    "OutgoingMessage",
    "log_unexpected_stop",
    "outbox_table",
    "run_outbox_relay",
]
