"""Получатели результатов: Kafka (рабочий режим) и журнал (разработка, без брокера).

Публикация в Kafka – напрямую, без outbox (у сервиса нет БД, отсчеты эфемерны – emotion-ml-service.md). Отправка
не блокирует такт анализа: сообщения ставятся в буфер производителя, подтверждения проверяются в фоне. Если
брокер недоступен или буфер переполнен, отсчеты отбрасываются со счетчиком ошибок, анализ продолжается.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from vks_contracts.envelope import EventPayload, kafka_headers

from emotion_service.events import envelope

log = logging.getLogger("emotion_service.events")


class ResultSink(Protocol):
    async def publish(self, payloads: Sequence[EventPayload]) -> None: ...

    async def aclose(self) -> None: ...


def encode(payload: EventPayload) -> tuple[str, bytes, bytes, list[tuple[str, bytes]]]:
    """Топик, ключ, значение (JSON-конверт) и заголовки сообщения Kafka (events.md, «Формат сообщения»)."""
    env = envelope(payload)
    return payload.topic.value, payload.key().encode("utf-8"), env.model_dump_json().encode("utf-8"), kafka_headers(env)


class LoggingSink:
    async def publish(self, payloads: Sequence[EventPayload]) -> None:
        for payload in payloads:
            topic, key, value, _ = encode(payload)
            log.info("%s key=%s %s", topic, key.decode(), value.decode("utf-8"))

    async def aclose(self) -> None:
        return None


class MemorySink:
    """Для тестов и спайка: накапливает (топик, ключ, конверт) в памяти."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def publish(self, payloads: Sequence[EventPayload]) -> None:
        for payload in payloads:
            topic, key, value, _ = encode(payload)
            self.events.append((topic, key.decode(), json.loads(value)))

    async def aclose(self) -> None:
        return None


class KafkaSink:
    """Производитель aiokafka: linger 20 мс, lz4, request_timeout 2 с (conventions.md, §6)."""

    def __init__(self, bootstrap_servers: str, client_id: str = "emotion-ml-service", producer: Any = None) -> None:
        if producer is None:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=bootstrap_servers,
                client_id=client_id,
                acks=1,  # отсчеты эфемерны: подтверждения лидера достаточно, задержка ниже, чем у acks=all
                linger_ms=20,
                compression_type="lz4",
                request_timeout_ms=2000,
            )
        self._producer = producer
        self._pending: set[asyncio.Future[Any]] = set()
        self.sent = 0
        self.errors = 0

    async def start(self) -> None:
        await self._producer.start()

    async def publish(self, payloads: Sequence[EventPayload]) -> None:
        for payload in payloads:
            topic, key, value, headers = encode(payload)
            try:
                delivery = await self._producer.send(topic, value=value, key=key, headers=headers)
            except Exception:  # буфер переполнен или брокер недоступен: отсчет теряется, анализ идет дальше
                self.errors += 1
                log.warning("Отсчет не поставлен в очередь Kafka", exc_info=True)
                continue
            self._pending.add(delivery)
            delivery.add_done_callback(self._delivered)

    def _delivered(self, delivery: asyncio.Future[Any]) -> None:
        self._pending.discard(delivery)
        if delivery.cancelled() or delivery.exception() is not None:
            self.errors += 1
        else:
            self.sent += 1

    async def aclose(self) -> None:
        await self._producer.stop()
