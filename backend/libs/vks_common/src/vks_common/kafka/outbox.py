"""Transactional outbox (ADR-011, conventions.md, §6).

Сценарий пишет событие :class:`OutboxWriter` в таблицу ``<схема>.outbox`` той же транзакцией, что и изменение
данных: событие не теряется при сбое между фиксацией и отправкой и не уходит из откатившейся транзакции.
:class:`OutboxRelay` – фоновая задача сервиса – забирает неотправленные записи по возрастанию ``id``, отправляет их
и отмечает ``published_at``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from aiokafka.errors import KafkaError
from sqlalchemy import (
    BigInteger,
    Column,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.kafka.producer import EventProducer, OutgoingMessage
from vks_common.logging import current_request_id, get_logger
from vks_contracts import EventEnvelope, EventPayload, envelope_for, kafka_headers

__all__ = ["OUTBOX_NOTIFY", "OutboxRelay", "OutboxWriter", "outbox_table"]

_logger = get_logger(__name__)

# Ключ ``session.info``: функция, которую нужно вызвать после фиксации транзакции с событиями, – она будит релей,
# чтобы событие ушло сразу, а не на следующем опросе. Кладет ее туда фабрика сессий сервиса.
OUTBOX_NOTIFY = "outbox_notify"


def outbox_table(metadata: MetaData) -> Table:
    """Таблица ``outbox`` в схеме метаданных сервиса (database.md, «Таблица outbox»)."""
    return Table(
        "outbox",
        metadata,
        Column("id", BigInteger, Identity(always=True), primary_key=True),
        Column("event_id", Uuid, nullable=False),
        Column("topic", Text, nullable=False),
        Column("event_key", Text, nullable=False),
        Column("event_type", Text, nullable=False),
        Column("envelope", JSONB, nullable=False),
        Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
        Column("published_at", TIMESTAMP(timezone=True)),
        Column("attempts", Integer, server_default="0", nullable=False),
        UniqueConstraint("event_id"),
        # Релей ищет только неотправленные: частичный индекс остается маленьким, сколько бы событий ни накопилось.
        Index("outbox_unpublished_idx", "id", postgresql_where=text("published_at IS NULL")),
    )


class OutboxWriter:
    """Запись событий в outbox в транзакции вызывающего сценария; сам не коммитит."""

    def __init__(self, session: AsyncSession, table: Table, *, producer: str) -> None:
        self._session = session
        self._table = table
        self._producer = producer

    async def add(self, payload: EventPayload, *, event_id: UUID, occurred_at: datetime) -> None:
        """Добавить событие. ``correlation_id`` – ``request_id`` текущего запроса (сквозная трассировка)."""
        envelope = envelope_for(
            payload,
            event_id=event_id,
            occurred_at=occurred_at,
            producer=self._producer,
            correlation_id=current_request_id(),
        )
        await self._session.execute(
            insert(self._table).values(
                event_id=envelope.event_id,
                topic=payload.topic.value,
                event_key=payload.key(),
                event_type=envelope.type,
                envelope=envelope.model_dump(mode="json"),
                created_at=occurred_at,
            )
        )
        notify = self._session.info.get(OUTBOX_NOTIFY)
        if callable(notify):
            _wake_after_commit(self._session.sync_session, notify)


# Флаг в ``session.info``: обработчик фиксации уже назначен – пачка событий одной транзакции будит релей один раз.
_WAKE_PENDING = "outbox_wake_pending"


def _wake_after_commit(session: Session, notify: Callable[[], None]) -> None:
    if session.info.get(_WAKE_PENDING):
        return
    session.info[_WAKE_PENDING] = True

    def after_commit(committed: Session) -> None:
        committed.info.pop(_WAKE_PENDING, None)
        notify()

    event.listen(session, "after_commit", after_commit, once=True)


class OutboxRelay:
    """Фоновая задача сервиса: неотправленные записи outbox → Kafka.

    Порядок внутри ключа сохраняется: записи идут по возрастанию ``id``, релей на сервис один, производитель
    идемпотентный. Повтор публикации возможен (сбой между подтверждением брокера и ``UPDATE``) – потребители
    идемпотентны по ``event_id``. Пачка выбирается ``FOR UPDATE SKIP LOCKED``: вторая копия релея не возьмет те же
    строки, а держит строки он только на время отправки пачки.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        table: Table,
        producer: EventProducer,
        clock: Clock,
        batch_size: int = 100,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._sessions = session_factory
        self._table = table
        self._producer = producer
        self._clock = clock
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._wakeup = asyncio.Event()

    def notify(self) -> None:
        """Разбудить релей: транзакция с событиями зафиксирована."""
        self._wakeup.set()

    async def run(self) -> None:
        """Работать до отмены: по сигналу или раз в ``poll_interval_seconds``.

        Недоступная БД не останавливает задачу: события дождутся в outbox, а цикл повторится на следующем такте.
        """
        while True:
            try:
                while await self.publish_pending() == self._batch_size:
                    pass  # полная пачка – скорее всего, есть еще
            except (SQLAlchemyError, OSError) as error:
                _logger.warning("outbox relay cycle failed", error=type(error).__name__)
            try:
                async with asyncio.timeout(self._poll_interval):
                    await self._wakeup.wait()
            except TimeoutError:
                pass
            self._wakeup.clear()

    async def publish_pending(self) -> int:
        """Отправить одну пачку. Возвращает, сколько записей опубликовано; ошибка Kafka – 0, записи остаются."""
        table = self._table
        async with self._sessions() as session, transaction(session):
            rows = (
                await session.execute(
                    select(table.c.id, table.c.topic, table.c.event_key, table.c.envelope)
                    .where(table.c.published_at.is_(None))
                    .order_by(table.c.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if not rows:
                return 0
            ids = [row.id for row in rows]
            messages = [_message(row.topic, row.event_key, row.envelope) for row in rows]
            try:
                await self._producer.send_all(messages)
            except (KafkaError, TimeoutError) as error:
                # Брокер недоступен или не подтвердил запись: записи остаются и уйдут на следующем цикле.
                await session.execute(update(table).where(table.c.id.in_(ids)).values(attempts=table.c.attempts + 1))
                _logger.warning("outbox publish failed", pending=len(ids), error=type(error).__name__)
                return 0
            await session.execute(update(table).where(table.c.id.in_(ids)).values(published_at=self._clock.now()))
        _logger.debug("outbox published", count=len(ids))
        return len(ids)


def _message(topic: str, key: str, stored_envelope: object) -> OutgoingMessage:
    envelope = EventEnvelope.model_validate(stored_envelope)
    return OutgoingMessage(
        topic=topic,
        key=key,
        value=json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).encode("utf-8"),
        headers=kafka_headers(envelope),
    )
