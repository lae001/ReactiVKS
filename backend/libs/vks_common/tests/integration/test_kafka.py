"""vks_common.kafka на настоящих PostgreSQL и Kafka: outbox → релей → брокер → потребитель (спайк 3, EMO-52)."""

import asyncio
import json
import statistics
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import MetaData, delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vks_common.clock import SystemClock
from vks_common.db import create_session_factory, transaction
from vks_common.ids import new_id
from vks_common.kafka import (
    OUTBOX_NOTIFY,
    EventConsumer,
    EventProducer,
    OutboxRelay,
    OutboxWriter,
    OutgoingMessage,
    outbox_table,
)
from vks_common.kafka.consumer import TemporaryFailure
from vks_contracts import ParsedEvent, envelope_for, kafka_headers
from vks_contracts.meeting_events import MeetingEnded

pytestmark = pytest.mark.integration

TOPIC = "meeting.events"
OUTBOX = outbox_table(MetaData(schema="auth"))

Received = list[ParsedEvent]


def meeting_ended(meeting_id: UUID | None = None) -> MeetingEnded:
    return MeetingEnded(meeting_id=meeting_id or uuid4(), ended_at=datetime.now(UTC), reason="organizer")


@pytest.fixture
async def sessions(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Настоящие транзакции, без отката: релей и сценарий должны видеть зафиксированное друг другом."""
    factory = create_session_factory(engine)
    yield factory
    async with factory() as session, transaction(session):
        await session.execute(delete(OUTBOX))


@pytest.fixture
async def producer(kafka_bootstrap: str) -> AsyncIterator[EventProducer]:
    producer = EventProducer(bootstrap_servers=kafka_bootstrap, client_id="test-producer")
    await producer.start()
    yield producer
    await producer.stop()


ConsumerFactory = Callable[..., Awaitable[tuple[EventConsumer, Received]]]


@pytest.fixture
async def make_consumer(kafka_bootstrap: str, producer: EventProducer) -> AsyncIterator[ConsumerFactory]:
    """Потребитель в своей группе; собирает обработанные события в список."""
    consumers: list[EventConsumer] = []

    async def make(
        *,
        topic: str = TOPIC,
        group_id: str | None = None,
        handler: Callable[[ParsedEvent], Awaitable[None]] | None = None,
    ) -> tuple[EventConsumer, Received]:
        received: Received = []

        async def collect(event: ParsedEvent) -> None:
            if handler is not None:
                await handler(event)
            received.append(event)

        consumer = EventConsumer(
            bootstrap_servers=kafka_bootstrap,
            topics=[topic],
            group_id=group_id or f"test-{uuid4().hex[:8]}",
            client_id="test-consumer",
            handler=collect,
            dead_letters=producer,
            clock=SystemClock(),
            retry_base_delay_seconds=0.01,
        )
        await consumer.start()
        consumers.append(consumer)
        return consumer, received

    yield make
    for consumer in consumers:
        await consumer.stop()


async def poll_until(consumer: EventConsumer, done: Callable[[], bool], *, within_seconds: float = 20.0) -> None:
    """Опрашивать, пока не выполнится условие; без time.sleep – ожидание опросом с таймаутом."""
    async with asyncio.timeout(within_seconds):
        while not done():
            await consumer.poll_once(timeout_ms=200)


def ids_of(received: Received) -> list[UUID]:
    return [event.envelope.event_id for event in received]


async def write(sessions: async_sessionmaker[AsyncSession], *payloads: MeetingEnded) -> list[UUID]:
    """Записать события в outbox одной транзакцией – так, как это делает сценарий."""
    event_ids = [new_id() for _ in payloads]
    async with sessions() as session, transaction(session):
        writer = OutboxWriter(session, OUTBOX, producer="test-service")
        for payload, event_id in zip(payloads, event_ids, strict=True):
            await writer.add(payload, event_id=event_id, occurred_at=datetime.now(UTC))
    return event_ids


def relay_for(sessions: async_sessionmaker[AsyncSession], producer: EventProducer) -> OutboxRelay:
    return OutboxRelay(session_factory=sessions, table=OUTBOX, producer=producer, clock=SystemClock())


async def test_event_reaches_consumer_through_outbox(
    sessions: async_sessionmaker[AsyncSession], producer: EventProducer, make_consumer: ConsumerFactory
) -> None:
    payload = meeting_ended()
    [event_id] = await write(sessions, payload)
    consumer, received = await make_consumer()

    published = await relay_for(sessions, producer).publish_pending()
    await poll_until(consumer, lambda: event_id in ids_of(received))

    assert published == 1
    event = next(event for event in received if event.envelope.event_id == event_id)
    assert event.payload == payload
    assert event.envelope.producer == "test-service"
    async with sessions() as session:
        published_at = await session.scalar(select(OUTBOX.c.published_at).where(OUTBOX.c.event_id == event_id))
    assert published_at is not None


async def test_rolled_back_transaction_publishes_nothing(
    sessions: async_sessionmaker[AsyncSession], producer: EventProducer
) -> None:
    async with sessions() as session:
        await session.begin()
        await OutboxWriter(session, OUTBOX, producer="test-service").add(
            meeting_ended(), event_id=new_id(), occurred_at=datetime.now(UTC)
        )
        await session.rollback()

    assert await relay_for(sessions, producer).publish_pending() == 0


async def test_events_of_one_meeting_keep_their_order(
    sessions: async_sessionmaker[AsyncSession], producer: EventProducer, make_consumer: ConsumerFactory
) -> None:
    meeting_id = uuid4()
    event_ids: list[UUID] = []
    for _ in range(20):
        event_ids += await write(sessions, meeting_ended(meeting_id))
    consumer, received = await make_consumer()

    await relay_for(sessions, producer).publish_pending()
    await poll_until(consumer, lambda: set(event_ids) <= set(ids_of(received)))

    assert [event_id for event_id in ids_of(received) if event_id in set(event_ids)] == event_ids


async def test_unknown_event_is_skipped_and_broken_one_goes_to_dead_letters(
    producer: EventProducer, make_consumer: ConsumerFactory
) -> None:
    good = envelope_for(meeting_ended(), event_id=new_id(), occurred_at=datetime.now(UTC), producer="test")
    unknown = good.model_copy(update={"event_id": new_id(), "type": "meeting.archived"})
    broken = good.model_copy(update={"event_id": new_id(), "payload": {"meeting_id": "not-a-uuid"}})
    await producer.send_all(
        [
            OutgoingMessage(TOPIC, "k", envelope.model_dump_json().encode(), kafka_headers(envelope))
            for envelope in (unknown, broken, good)
        ]
    )
    consumer, received = await make_consumer()
    dead_letters, _ = await make_consumer(topic=f"{TOPIC}.dlq")

    await poll_until(consumer, lambda: good.event_id in ids_of(received))

    assert unknown.event_id not in ids_of(received)
    assert broken.event_id not in ids_of(received)
    # Сообщение в DLQ нарушает контракт – обработчик его не увидит; проверяем сырые записи брокера.
    raw: list[dict[str, object]] = []

    async def read_raw() -> bool:
        records = await dead_letters._consumer.getmany(timeout_ms=200)  # noqa: SLF001 - сырой доступ к DLQ в тесте
        for batch in records.values():
            raw.extend({"value": json.loads(record.value), "headers": dict(record.headers)} for record in batch)
        return any(item["value"]["event_id"] == str(broken.event_id) for item in raw)  # type: ignore[index]

    async with asyncio.timeout(20):
        while not await read_raw():
            pass
    moved = next(item for item in raw if item["value"]["event_id"] == str(broken.event_id))  # type: ignore[index]
    headers = moved["headers"]
    assert isinstance(headers, dict)
    assert headers["source_topic"] == TOPIC.encode()
    assert b"does not match the contract" in headers["error"]


async def test_temporary_failure_is_retried_and_offset_committed_after_success(
    sessions: async_sessionmaker[AsyncSession], producer: EventProducer, make_consumer: ConsumerFactory
) -> None:
    [event_id] = await write(sessions, meeting_ended())
    await relay_for(sessions, producer).publish_pending()
    attempts: list[UUID] = []
    group_id = f"test-{uuid4().hex[:8]}"

    async def flaky(event: ParsedEvent) -> None:
        if event.envelope.event_id == event_id:
            attempts.append(event_id)
            if len(attempts) < 3:
                raise TemporaryFailure("database is unavailable")

    consumer, received = await make_consumer(group_id=group_id, handler=flaky)
    await poll_until(consumer, lambda: event_id in ids_of(received))
    await consumer.stop()
    again, received_again = await make_consumer(group_id=group_id)
    await again.poll_once(timeout_ms=2000)

    assert len(attempts) == 3
    assert event_id not in ids_of(received_again)


async def test_outbox_to_consumer_latency_is_under_a_second(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    producer: EventProducer,
    make_consumer: ConsumerFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Критерий спайка 3: событие доходит от фиксации транзакции до потребителя быстрее 1 с.

    Релей работает фоном и просыпается по сигналу после фиксации (``OUTBOX_NOTIFY``), а не только раз в секунду.
    """
    relay = relay_for(sessions, producer)
    notifying = create_session_factory(engine, info={OUTBOX_NOTIFY: relay.notify})
    consumer, received = await make_consumer()
    await consumer.poll_once(timeout_ms=2000)  # дождаться назначения партиций
    committed_at: dict[UUID, float] = {}
    arrived_at: dict[UUID, float] = {}
    all_written = asyncio.Event()
    all_arrived = asyncio.Event()

    async def consume() -> None:
        while True:
            await consumer.poll_once(timeout_ms=50)
            for event in received:
                arrived_at.setdefault(event.envelope.event_id, time.monotonic())
            if all_written.is_set() and set(committed_at) <= set(arrived_at):
                all_arrived.set()

    relay_task = asyncio.create_task(relay.run())
    consume_task = asyncio.create_task(consume())
    try:
        for _ in range(100):
            [event_id] = await write(notifying, meeting_ended())
            committed_at[event_id] = time.monotonic()
            await asyncio.sleep(0.02)
        all_written.set()
        async with asyncio.timeout(20):
            await all_arrived.wait()
    finally:
        relay_task.cancel()
        consume_task.cancel()
        await asyncio.gather(relay_task, consume_task, return_exceptions=True)

    latencies = sorted(arrived_at[event_id] - committed_at[event_id] for event_id in committed_at)
    p50, p95 = statistics.median(latencies), latencies[int(len(latencies) * 0.95) - 1]
    with capsys.disabled():
        sys.stdout.write(
            f"\noutbox → consumer, {len(latencies)} событий: p50={p50 * 1000:.1f} мс, "
            f"p95={p95 * 1000:.1f} мс, max={latencies[-1] * 1000:.1f} мс\n"
        )
    assert p95 < 1.0
