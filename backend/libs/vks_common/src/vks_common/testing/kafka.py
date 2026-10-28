"""Kafka для интеграционных тестов.

Образ – сборка Confluent (``cp-kafka``) в режиме KRaft: ее умеет запускать ``KafkaContainer`` testcontainers, а
протокол тот же, что у ``apache/kafka`` из docker-compose.dev.yml. Топики создаются автоматически – тесты
используют уникальные группы потребителей и различают свои сообщения по ``event_id``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from testcontainers.community.kafka import KafkaContainer

__all__ = ["KAFKA_IMAGE", "start_kafka"]

KAFKA_IMAGE = "confluentinc/cp-kafka:7.6.0"


@contextmanager
def start_kafka() -> Iterator[str]:
    """Запустить брокер и вернуть адрес для ``bootstrap_servers``; остановить по выходе."""
    with KafkaContainer(KAFKA_IMAGE).with_kraft() as container:
        yield container.get_bootstrap_server()
