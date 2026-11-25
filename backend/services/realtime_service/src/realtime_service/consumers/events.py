"""Kafka для оперативного состояния: фильтрация по ключу до декодирования."""

import asyncio
from uuid import UUID

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from realtime_service.services.live_rooms import LiveRooms
from vks_common.logging import get_logger
from vks_contracts import IncompatibleEvent, Topic, UnknownEvent, parse_event
from vks_contracts.envelope import MeetingKeyed

_logger = get_logger(__name__)


async def consume_events(rooms: LiveRooms, *, bootstrap_servers: str, instance: str) -> None:
    while True:
        consumer = AIOKafkaConsumer(
            Topic.EMOTION_SAMPLES,
            Topic.ML_STATUS,
            Topic.MEETING_EVENTS,
            Topic.REPORT_EVENTS,
            bootstrap_servers=bootstrap_servers,
            client_id="realtime-service",
            group_id=f"realtime-{instance}",
            auto_offset_reset="latest",
            enable_auto_commit=True,
            fetch_max_wait_ms=50,
            fetch_min_bytes=1,
        )
        try:
            await consumer.start()
            async for record in consumer:
                route_event(rooms, key=record.key, value=record.value)
        except KafkaError as error:
            _logger.warning("realtime kafka disconnected", error=type(error).__name__)
        finally:
            await consumer.stop()
        await asyncio.sleep(2)


def route_event(rooms: LiveRooms, *, key: bytes | None, value: bytes | None) -> None:
    if key is None or value is None:
        return
    try:
        meeting_id = UUID(key.decode())
    except ValueError:
        return
    room = rooms.tracked(meeting_id)
    if room is None:
        return
    try:
        event = parse_event(value)
    except (UnknownEvent, IncompatibleEvent) as error:
        _logger.warning("realtime event skipped", error=type(error).__name__)
        return
    if isinstance(event.payload, MeetingKeyed) and event.payload.meeting_id == meeting_id:
        room.apply(event)
