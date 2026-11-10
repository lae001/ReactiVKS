"""Нагрузочный тест агента (EMO-93): M встреч × N участников с видео на локальном LiveKit.

Каждый участник публикует 640×360, 15 кадр/с (лицо из --image, слегка смещается) и дает согласие; агент
диспетчеризуется в каждую встречу с {"fps": --fps}. Во время теста раз в секунду снимаются CPU и память процессов
агента (psutil, по командной строке «emotion-agent»). После теста журнал агента (LoggingSink, JSON) разбирается:
фактическая частота по встречам, задержка «кадр получен → событие собрано» (occurred_at − ts), доля отсчетов с
лицом, состояния ml.status.

Ограничение: участники-публикаторы работают на той же машине и тоже занимают CPU (кодирование VP8) – замер
агента консервативный (на сервере агент делит CPU только с LiveKit).

  livekit-server --dev
  ML_LOAD_THRESHOLD=0.95 emotion-agent start > agent.log 2>&1
  python scripts/load_test.py --image face.png --meetings 1 --participants 10 --seconds 60 --agent-log agent.log
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import psutil
from e2e_livekit import KEY, SECRET, URL, publish_camera, token
from livekit import api, rtc


async def run_meeting(lkapi: api.LiveKitAPI, face: object, participants: int, fps: int, stop: asyncio.Event) -> str:
    room_name = str(uuid.uuid4())
    rooms, tasks = [], []
    for i in range(participants):
        room = rtc.Room()
        await room.connect(URL, token(room_name, f"p_{uuid.uuid4()}", f"Участник {i + 1}", "granted"))
        rooms.append(room)
        tasks.append(asyncio.create_task(publish_camera(room, face, stop)))  # type: ignore[arg-type]
        # Публикации по очереди: десятки одновременных publish_track из одного процесса не успевают получить
        # подтверждение сервера (ограничение стенда, а не агента).
        await asyncio.sleep(0.7)
    await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name="emotion-agent", room=room_name, metadata=json.dumps({"fps": fps}))
    )
    await stop.wait()
    await asyncio.gather(*tasks)
    for room in rooms:
        await room.disconnect()
    await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
    return room_name


def agent_processes() -> list[psutil.Process]:
    found = []
    for proc in psutil.process_iter(["cmdline"]):
        cmdline = " ".join(proc.info.get("cmdline") or [])
        if "emotion-agent" in cmdline or "emotion_service.agent" in cmdline:
            found.append(proc)
    return found


async def sample_resources(stop: asyncio.Event, out: list[tuple[float, float]]) -> None:
    """CPU и память воркера вместе с процессами заданий (по процессу на встречу) – раз в секунду."""
    known: dict[int, psutil.Process] = {}
    while not stop.is_set():
        for root in agent_processes():
            for proc in [root, *root.children(recursive=True)]:
                if proc.pid not in known:
                    proc.cpu_percent(None)
                    known[proc.pid] = proc
        await asyncio.sleep(1)
        cpu = mem = 0.0
        for proc in list(known.values()):
            try:
                cpu += proc.cpu_percent(None)
                mem += proc.memory_info().rss / 2**20
            except psutil.NoSuchProcess:
                known.pop(proc.pid, None)
        out.append((cpu, mem))


def summarize(log_path: Path, rooms: list[str], seconds: float, participants: int) -> dict[str, object]:
    delays: list[float] = []
    per_room: dict[str, dict[str, float]] = {r: {"samples": 0, "faces": 0} for r in rooms}
    statuses: dict[str, list[float]] = {r: [] for r in rooms}
    degraded = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            message = json.loads(line).get("message", "")
        except json.JSONDecodeError:
            continue
        if not message.startswith(("emotion.samples", "ml.status")):
            continue
        event = json.loads(message.split(" ", 2)[2])
        payload = event["payload"]
        room = payload["meeting_id"]
        if room not in per_room:
            continue
        if event["type"] == "ml.status":
            if payload["state"] == "active" and payload["effective_fps"] > 0:
                statuses[room].append(payload["effective_fps"])
            degraded += payload["state"] == "degraded"
            continue
        per_room[room]["samples"] += 1
        per_room[room]["faces"] += payload["state"] == "analyzing"
        occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
        received = datetime.fromisoformat(payload["ts"].replace("Z", "+00:00"))
        delays.append((occurred - received).total_seconds() * 1000)
    delays.sort()

    def pct(q: float) -> float:
        return round(delays[min(len(delays) - 1, int(q * len(delays)))], 1) if delays else float("nan")

    return {
        "samples_per_participant_per_s": {
            r[:8]: round(v["samples"] / seconds / participants, 2) for r, v in per_room.items()
        },
        "face_ratio": {r[:8]: round(v["faces"] / max(v["samples"], 1), 3) for r, v in per_room.items()},
        "effective_fps_mean": {r[:8]: round(statistics.mean(v), 2) if v else None for r, v in statuses.items()},
        "delay_ms": {"p50": pct(0.5), "p95": pct(0.95), "max": pct(1.0), "n": len(delays)},
        "degraded_status_events": degraded,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--meetings", type=int, default=1)
    parser.add_argument("--participants", type=int, default=10)
    parser.add_argument("--fps", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--agent-log", required=True)
    parser.add_argument("--out", default="load_test_result.json")
    args = parser.parse_args()
    face = cv2.cvtColor(cv2.imread(args.image), cv2.COLOR_BGR2RGB)

    lkapi = api.LiveKitAPI(URL.replace("ws", "http", 1), KEY, SECRET)
    stop = asyncio.Event()
    resources: list[tuple[float, float]] = []
    meetings = []
    for _ in range(args.meetings):
        meetings.append(asyncio.create_task(run_meeting(lkapi, face, args.participants, args.fps, stop)))
        await asyncio.sleep(args.participants * 0.7 + 2)
    await asyncio.sleep(5)  # диспетчеризация и подписки последней встречи
    sampler = asyncio.create_task(sample_resources(stop, resources))
    started = time.monotonic()
    await asyncio.sleep(args.seconds)
    elapsed = time.monotonic() - started
    stop.set()
    rooms = await asyncio.gather(*meetings)
    await sampler
    await lkapi.aclose()
    await asyncio.sleep(2)

    cpu = [c for c, _ in resources]
    result = {
        "meetings": args.meetings,
        "participants_per_meeting": args.participants,
        "target_fps": args.fps,
        "seconds": round(elapsed, 1),
        "logical_cpus": psutil.cpu_count(),
        "agent_cpu_percent": {"mean": round(statistics.mean(cpu), 1), "max": round(max(cpu), 1)} if cpu else None,
        "agent_rss_mb_max": round(max(m for _, m in resources), 1) if resources else None,
        **summarize(Path(args.agent_log), list(rooms), elapsed + 5, args.participants),
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")  # noqa: ASYNC240
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
