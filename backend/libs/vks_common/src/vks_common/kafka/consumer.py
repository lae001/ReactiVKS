"""Потребитель событий (conventions.md, §7): ручная фиксация смещений после обработки, повторы и DLQ.

Сообщения одной партиции обрабатываются последовательно – порядок внутри ключа сохраняется. Смещение фиксируется
только после успешной обработки (или переноса в DLQ): при сбое процесса необработанное сообщение будет прочитано
снова, поэтому обработчик обязан быть идемпотентным по ``event_id``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from aiokafka import AIOKafkaConsumer, ConsumerRecord, TopicPartition
from aiokafka.errors import KafkaError

from vks_common.clock import Clock
from vks_common.kafka.producer import EventProducer, OutgoingMessage
from vks_common.logging import get_logger
from vks_contracts import IncompatibleEvent, ParsedEvent, UnknownEvent, parse_event

__all__ = ["EventConsumer", "EventHandler", "TemporaryFailure"]

_logger = get_logger(__name__)

EventHandler = Callable[[ParsedEvent], Awaitable[None]]


class TemporaryFailure(Exception):
    """Обработчик не справился по временной причине (БД, внутренний REST): сообщение будет повторено."""


class EventConsumer:
    """Группа потребителей над ``AIOKafkaConsumer`` с ручной фиксацией смещений.

    - неизвестный тип или версия – ``warning`` и пропуск (tolerant reader);
    - нарушение контракта или постоянная ошибка обработчика – сообщение в ``<топик>.dlq``, обработка идет дальше;
    - :class:`TemporaryFailure` – повтор с задержкой 0,5 → 1 → 2 … с без продвижения смещения, после
      ``max_attempts`` – тоже в DLQ.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topics: Sequence[str],
        group_id: str,
        client_id: str,
        handler: EventHandler,
        dead_letters: EventProducer,
        clock: Clock,
        auto_offset_reset: str = "earliest",
        max_attempts: int = 5,
        retry_base_delay_seconds: float = 0.5,
    ) -> None:
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            enable_auto_commit=False,
            auto_offset_reset=auto_offset_reset,
            isolation_level="read_committed",
            max_poll_records=500,
        )
        self._handler = handler
        self._dead_letters = dead_letters
        self._clock = clock
        self._max_attempts = max_attempts
        self._retry_base_delay = retry_base_delay_seconds

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def run(self) -> None:
        """Работать до отмены."""
        while True:
            await self.poll_once()

    async def poll_once(self, timeout_ms: int = 1000) -> int:
        """Одна выборка: обработать пачки всех партиций и зафиксировать смещения. Возвращает число сообщений."""
        batches: dict[TopicPartition, list[ConsumerRecord[bytes, bytes]]] = await self._consumer.getmany(
            timeout_ms=timeout_ms
        )
        handled = 0
        for partition, records in batches.items():
            for record in records:
                await self._process(record)
                handled += 1
            await self._consumer.commit({partition: records[-1].offset + 1})
        return handled

    async def _process(self, record: ConsumerRecord[bytes, bytes]) -> None:
        value = record.value or b""
        try:
            parsed = parse_event(value)
        except UnknownEvent as error:
            _logger.warning("event skipped", topic=record.topic, reason=str(error))
            return
        except IncompatibleEvent as error:
            await self._send_to_dead_letters(record, reason=str(error))
            return

        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._handler(parsed)
            except TemporaryFailure as error:
                if attempt == self._max_attempts:
                    await self._send_to_dead_letters(record, reason=f"temporary failure persisted: {error}")
                    return
                delay = min(self._retry_base_delay * 2 ** (attempt - 1), 30.0)
                _logger.warning("event handling failed, retrying", event_type=parsed.envelope.type, attempt=attempt)
                await asyncio.sleep(delay)
            else:
                return

    async def _send_to_dead_letters(self, record: ConsumerRecord[bytes, bytes], *, reason: str) -> None:
        headers = [
            *(record.headers or ()),
            ("error", reason.encode("utf-8")),
            ("failed_at", self._clock.now().isoformat().encode("ascii")),
            ("source_topic", record.topic.encode("utf-8")),
            ("source_partition", str(record.partition).encode("ascii")),
            ("source_offset", str(record.offset).encode("ascii")),
        ]
        message = OutgoingMessage(
            topic=f"{record.topic}.dlq",
            key=(record.key or b"").decode("utf-8", errors="replace"),
            value=record.value or b"",
            headers=list(headers),
        )
        try:
            await self._dead_letters.send_all([message])
        except KafkaError:
            # Без DLQ сообщение потеряется при фиксации смещения: пусть процесс упадет и прочитает его снова.
            _logger.error("dead letter not delivered", topic=record.topic, offset=record.offset)
            raise
        _logger.error("event moved to dead letters", topic=record.topic, offset=record.offset, reason=reason)
