"""Получатели результатов. Публикация в Kafka (emotion.samples, ml.status) подключается следующим спринтом
через тот же порт ResultSink; пока результаты пишутся в журнал JSON-строками."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

log = logging.getLogger("emotion_service.events")


class ResultSink(Protocol):
    async def publish(self, topic: str, key: str, events: list[dict[str, Any]]) -> None: ...

    async def aclose(self) -> None: ...


class LoggingSink:
    async def publish(self, topic: str, key: str, events: list[dict[str, Any]]) -> None:
        for event in events:
            log.info("%s key=%s %s", topic, key, json.dumps(event, ensure_ascii=False))

    async def aclose(self) -> None:
        return None


class MemorySink:
    """Для тестов и спайка: накапливает события в памяти."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def publish(self, topic: str, key: str, events: list[dict[str, Any]]) -> None:
        self.events.extend((topic, key, e) for e in events)

    async def aclose(self) -> None:
        return None
