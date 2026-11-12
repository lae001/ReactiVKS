"""Буфер партиций и фиксация смещений после транзакции записи."""

import asyncio
from collections.abc import Collection
from uuid import UUID

from aiokafka import AIOKafkaConsumer, ConsumerRebalanceListener, ConsumerRecord, TopicPartition
from aiokafka.errors import KafkaError
from sqlalchemy.exc import SQLAlchemyError

from analytics_service.domain.series import BufferedSample, Sample
from analytics_service.services.series import FlushSamples
from vks_common.clock import Clock
from vks_common.logging import get_logger
from vks_contracts import IncompatibleEvent, Topic, UnknownEvent, parse_event
from vks_contracts.ml_events import EMOTIONS, EmotionSample

_logger = get_logger(__name__)


class SampleConsumer(ConsumerRebalanceListener):  # type: ignore[misc]  # у aiokafka нет заглушек.
    def __init__(self, *, bootstrap_servers: str, flush: FlushSamples, clock: Clock) -> None:
        self._bootstrap = bootstrap_servers
        self._flush = flush
        self._clock = clock
        self._consumer: AIOKafkaConsumer | None = None
        self._pending: dict[TopicPartition, list[BufferedSample]] = {}
        self._lock = asyncio.Lock()

    async def run(self) -> None:
        while True:
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap,
                group_id="analytics",
                client_id="analytics-samples",
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                max_poll_records=1000,
            )
            consumer.subscribe([Topic.EMOTION_SAMPLES], listener=self)
            self._consumer = consumer
            try:
                await consumer.start()
                while True:
                    batches = await consumer.getmany(timeout_ms=250)
                    offsets: dict[TopicPartition, int] = {}
                    async with self._lock:
                        now = self._clock.now()
                        for partition, records in batches.items():
                            pending = self._pending.setdefault(partition, [])
                            pending.extend(BufferedSample(record.offset, now, _sample(record)) for record in records)
                            if len(pending) >= 10000:
                                consumer.pause(partition)
                        for partition in list(self._pending):
                            offset = await self._persist(partition)
                            if offset is not None:
                                offsets[partition] = offset
                    if offsets:
                        await consumer.commit(offsets)
            except (KafkaError, SQLAlchemyError) as error:
                _logger.warning("analytics samples retrying", error=type(error).__name__)
            finally:
                self._consumer = None
                await consumer.stop()
                self._pending.clear()
            await asyncio.sleep(1)

    async def on_partitions_assigned(self, assigned: Collection[TopicPartition]) -> None:
        """Позиции восстанавливаются из Kafka и транзакционной границы в PostgreSQL."""

    async def on_partitions_revoked(self, revoked: Collection[TopicPartition]) -> None:
        async with self._lock:
            for partition in revoked:
                try:
                    offset = await self._persist(partition, force=True)
                    if self._consumer is not None and offset is not None:
                        await self._consumer.commit({partition: offset})
                except (KafkaError, SQLAlchemyError) as error:
                    _logger.warning("samples remain uncommitted", error=type(error).__name__)
                finally:
                    self._pending.pop(partition, None)

    async def _persist(self, partition: TopicPartition, *, force: bool = False) -> int | None:
        consumer = self._consumer
        pending = self._pending.get(partition)
        if consumer is None or not pending:
            return None
        result = await self._flush.execute(partition.partition, pending, now=self._clock.now(), force=force)
        if result.consumed:
            del pending[: result.consumed]
            if len(pending) < 10000 and partition in consumer.paused():
                consumer.resume(partition)
            return result.next_offset
        return None


def _sample(record: ConsumerRecord[bytes, bytes]) -> Sample | None:
    try:
        payload = parse_event(record.value or b"").payload
        key = UUID((record.key or b"").decode())
    except (IncompatibleEvent, UnknownEvent, ValueError):
        _logger.warning("invalid emotion sample skipped", partition=record.partition, offset=record.offset)
        return None
    if not isinstance(payload, EmotionSample) or payload.meeting_id != key or payload.state == "no_consent":
        return None
    probabilities = payload.probs.model_dump() if payload.probs is not None else None
    return Sample(
        payload.meeting_id,
        payload.participant_id,
        payload.ts,
        tuple(probabilities[label] for label in EMOTIONS) if probabilities is not None else None,
        payload.model_version,
    )
