"""Нагрузка полного стенда 5×10: REST → LiveKit → ML → Kafka → WebSocket → отчет."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiohttp
import cv2
import psutil
from aiokafka import AIOKafkaConsumer
from e2e_livekit import URL, publish_camera
from livekit import rtc


async def run(image: Path, output: Path, seconds: int, count: int, participants: int) -> None:
    face = cv2.imread(str(image))
    if face is None:
        raise ValueError("Face image cannot be read")
    messages: list[dict] = []
    updates: list[tuple[float, dict]] = []
    rooms: list[rtc.Room] = []
    meeting_ids: list[str] = []
    tasks: list[asyncio.Task] = []
    stop = asyncio.Event()
    consumer = AIOKafkaConsumer(
        "emotion.samples",
        "ml.status",
        bootstrap_servers="localhost:9092",
        group_id=f"s6-load-{uuid4()}",
        auto_offset_reset="latest",
    )
    await consumer.start()

    async def collect() -> None:
        async for record in consumer:
            message = json.loads(record.value)
            if message["payload"]["meeting_id"] in meeting_ids:
                messages.append(message)

    async def ws_read(ws: aiohttp.ClientWebSocketResponse) -> None:
        async for message in ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(message.data)
                if data["type"] == "emotion.update":
                    updates.append((time.time(), data))
                elif data["type"] == "welcome":
                    for meeting_id in meeting_ids:
                        await ws.send_json({"type": "subscribe", "meeting_id": meeting_id})

    tasks.append(asyncio.create_task(collect()))
    samples: list[float] = []
    start = 0.0
    email = f"load-{uuid4().hex[:8]}@example.ru"
    password = "Load-check-" + uuid4().hex
    async with aiohttp.ClientSession() as http:

        async def api(path: str, data: dict | None = None, bearer: str = "", method: str = "POST") -> dict:
            async with http.request(
                method,
                "http://localhost:5173/api/v1/" + path,
                json=data,
                headers={"Authorization": "Bearer " + bearer} if bearer else {},
            ) as response:
                response.raise_for_status()
                return await response.json() if response.status != 204 else {}

        await api("auth/register", {"email": email, "password": password, "display_name": "Нагрузка S6"})
        token = (await api("auth/login", {"email": email, "password": password}))["access_token"]
        try:
            for index in range(count):
                meeting = await api("meetings", {"title": f"Нагрузка S6 #{index + 1}", "analysis_enabled": True}, token)
                meeting_ids.append(meeting["id"])
                owner = await api(f"meetings/{meeting['id']}/join", {"consent": "granted"}, token)
                joined = [owner]
                for number in range(participants - 1):
                    joined.append(
                        await api(
                            f"join/{meeting['invite_code']}",
                            {"display_name": f"Гость {number + 1}", "consent": "granted", "notice_version": "v1-draft"},
                        )
                    )
                for person in joined:
                    room = rtc.Room()
                    await room.connect(URL, person["livekit_token"], options=rtc.RoomOptions(auto_subscribe=False))
                    rooms.append(room)
                    tasks.append(asyncio.create_task(publish_camera(room, face, stop)))
                    await asyncio.sleep(0.25)
                print(f"Connected meeting {index + 1}: {len(rooms)} publishers", flush=True)
            async with http.ws_connect("http://localhost:5173/ws", protocols=["vks.v1"]) as ws:
                await ws.send_json({"type": "auth", "token": token})
                tasks.append(asyncio.create_task(ws_read(ws)))
                start = time.time()
                for _ in range(seconds):
                    samples.append(psutil.cpu_percent())
                    await asyncio.sleep(1)
            stop.set()
            report_start = time.monotonic()
            for meeting_id in meeting_ids:
                await api(f"meetings/{meeting_id}/end", {}, token)
            reports = []
            for _ in range(90):
                reports = [await api(f"reports/{identity}", bearer=token, method="GET") for identity in meeting_ids]
                if all(report["status"] in ("ready", "failed") for report in reports):
                    break
                await asyncio.sleep(1)
            period = [
                m
                for m in messages
                if m["type"] == "emotion.sample" and datetime.fromisoformat(m["payload"]["ts"]).timestamp() >= start
            ]
            analyzed = [m for m in period if m["payload"]["state"] == "analyzing"]
            counts = Counter(m["payload"]["participant_id"] for m in analyzed)
            delays = [
                at - datetime.fromisoformat(item["ts"]).timestamp()
                for at, update in updates
                for item in update["items"]
                if item.get("p")
            ]
            result = {
                "date": datetime.now(UTC).isoformat(),
                "meetings": meeting_ids,
                "participants": len(rooms),
                "seconds": seconds,
                "analyzing_samples": len(analyzed),
                "participants_analyzed": len(counts),
                "analyzed_per_meeting": dict(Counter(m["payload"]["meeting_id"] for m in analyzed)),
                "fps_per_participant": {key: value / seconds for key, value in counts.items()},
                "websocket_updates": len(updates),
                "latency_p50_s": statistics.median(delays) if delays else None,
                "latency_p95_s": sorted(delays)[int(len(delays) * 0.95)] if delays else None,
                "cpu_mean_percent": statistics.mean(samples),
                "cpu_peak_percent": max(samples),
                "reports": [report["status"] for report in reports],
                "report_analyzed_participants": [
                    sum(p["analyzed_seconds"] > 0 for p in report.get("summary", {}).get("participants", []))
                    for report in reports
                ],
                "reports_wait_s": time.monotonic() - report_start,
            }
            await asyncio.to_thread(
                output.write_text, json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False))
        finally:
            stop.set()
            for identity in meeting_ids:
                await api(f"meetings/{identity}/end", {}, token)
            for room in rooms:
                await room.disconnect()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await consumer.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--meetings", type=int, default=5)
    parser.add_argument("--participants", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run(args.image, args.output, args.seconds, args.meetings, args.participants))


if __name__ == "__main__":
    main()
