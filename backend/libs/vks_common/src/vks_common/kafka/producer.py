"""Производитель событий: идемпотентный, ``acks=all`` (conventions.md, §6)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from aiokafka import AIOKafkaProducer

from vks_common.logging import get_logger

__all__ = ["EventProducer", "OutgoingMessage"]

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    """Готовое к отправке сообщение: топик, ключ упорядочивания, JSON-конверт и заголовки."""

    topic: str
    key: str
    value: bytes
    headers: list[tuple[str, bytes]] = field(default_factory=list)


class EventProducer:
    """Обертка над ``AIOKafkaProducer`` с параметрами проекта.

    ``enable_idempotence`` исключает дубли при повторной отправке одним производителем, а не более 5 запросов в
    полете сохраняют порядок внутри ключа и при повторах.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        client_id: str,
        linger_ms: int = 5,
        request_timeout_ms: int = 5000,
        compression_type: str | None = "lz4",
    ) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            acks="all",
            enable_idempotence=True,
            linger_ms=linger_ms,
            request_timeout_ms=request_timeout_ms,
            compression_type=compression_type,
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def check(self) -> None:
        """Проверка для ``/ready``: брокер отдает метаданные кластера."""
        await self._producer.client.fetch_all_metadata()

    async def send_all(self, messages: Sequence[OutgoingMessage]) -> None:
        """Отправить пачку и дождаться подтверждения брокера по каждому сообщению.

        Сообщения ставятся в очередь по порядку, затем подтверждения ожидаются вместе: так пачка уходит за несколько
        запросов, а не за запрос на сообщение. Ошибка любого сообщения – исключение: пачка считается неотправленной.
        """
        deliveries = [
            await self._producer.send(
                message.topic,
                value=message.value,
                key=message.key.encode("utf-8"),
                headers=message.headers,
            )
            for message in messages
        ]
        await asyncio.gather(*deliveries)
