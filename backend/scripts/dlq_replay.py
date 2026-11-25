"""Контролируемое воспроизведение DLQ до зафиксированной границы; по умолчанию только просмотр."""

import argparse
import asyncio
import sys

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from vks_contracts import Topic, parse_event


async def replay(bootstrap: str, topic: str, limit: int, execute: bool) -> int:
    consumer = AIOKafkaConsumer(
        topic + ".dlq",
        bootstrap_servers=bootstrap,
        group_id=None,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        isolation_level="read_committed",
    )
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, enable_idempotence=True) if execute else None
    sent = 0
    await consumer.start()
    try:
        from aiokafka import TopicPartition

        partitions = consumer.partitions_for_topic(topic + ".dlq")
        if partitions is None:
            raise ValueError("DLQ does not exist")
        assignment = [TopicPartition(topic + ".dlq", p) for p in sorted(partitions)]
        consumer.unsubscribe()
        consumer.assign(assignment)
        await consumer.seek_to_beginning()
        ends = await consumer.end_offsets(assignment)
        if producer is not None:
            await producer.start()
        while sent < limit:
            batches = await consumer.getmany(timeout_ms=1000, max_records=min(500, limit - sent))
            for partition, records in batches.items():
                for record in records:
                    if record.offset >= ends[partition]:
                        continue
                    event = parse_event(record.value or b"")
                    if event.payload.topic != topic:
                        raise ValueError("Event topic differs from the selected source")
                    if producer is not None:
                        await producer.send_and_wait(
                            topic, key=record.key, value=record.value, headers=list(record.headers or ())
                        )
                    sent += 1
                    if sent >= limit:
                        break
            positions = await asyncio.gather(*(consumer.position(partition) for partition in ends))
            if all(position >= end for position, end in zip(positions, ends.values(), strict=True)):
                break
    finally:
        await consumer.stop()
        if producer is not None:
            await producer.stop()
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", choices=[topic.value for topic in Topic])
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    count = asyncio.run(replay(args.bootstrap, args.topic, args.limit, args.execute))
    sys.stdout.write(f"{count}\n")


if __name__ == "__main__":
    main()
