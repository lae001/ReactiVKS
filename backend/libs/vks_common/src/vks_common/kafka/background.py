"""Фоновые задачи Kafka в ``lifespan`` сервиса: подключение к брокеру с повторами и работа до отмены.

Брокер – некритичная зависимость сервисов с outbox (conventions.md, §10): пока он недоступен, сервис отвечает на
запросы, а события копятся в outbox. Поэтому подключение не останавливает запуск, а повторяется в фоне.
"""

from __future__ import annotations

import asyncio

from aiokafka.errors import KafkaError

from vks_common.kafka.outbox import OutboxRelay
from vks_common.kafka.producer import EventProducer
from vks_common.logging import get_logger

__all__ = ["log_unexpected_stop", "run_outbox_relay"]

_logger = get_logger(__name__)

# Пауза между попытками подключиться к брокеру, пока он недоступен.
RECONNECT_SECONDS = 5.0


async def run_outbox_relay(
    producer: EventProducer, relay: OutboxRelay, *, reconnect_seconds: float = RECONNECT_SECONDS
) -> None:
    """Подключить производителя (повторяя, пока брокер недоступен) и отправлять события из outbox до отмены."""
    while True:
        try:
            await producer.start()
            break
        except KafkaError as error:
            _logger.warning("kafka unavailable, retrying", error=type(error).__name__)
            await asyncio.sleep(reconnect_seconds)
    _logger.info("outbox relay started")
    await relay.run()


def log_unexpected_stop(task: asyncio.Task[None]) -> None:
    """``add_done_callback`` фоновой задачи: остановка не по отмене – в журнал, нужен человек."""
    if not task.cancelled() and task.exception() is not None:
        _logger.error("background task stopped", task=task.get_name(), error=type(task.exception()).__name__)
