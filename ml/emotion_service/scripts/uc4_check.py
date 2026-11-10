"""Внутреннее тестирование UC-4 со стороны ML-модуля (EMO-79): основной и альтернативные сценарии на живом LiveKit.

Участники: Анна (согласие, лицо), Борис (отказ от анализа), Вера (согласие, в кадре нет лица). Шаги по времени
(доли --seconds): 0 – диспетчеризация агента; 0,25 – Анна выключает камеру на 4 с; 0,6 – Анна отзывает согласие;
--kill-agent – в середине теста скрипт завершает процессы агента (альтернатива «отказ ML»: видеосвязь должна
продолжаться). По журналу агента выставляется результат каждой проверки.

  livekit-server --dev
  emotion-agent start > agent.log 2>&1
  python scripts/uc4_check.py --image face.png --agent-log agent.log [--kill-agent]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import psutil
from e2e_livekit import KEY, SECRET, URL, publish_camera, token
from livekit import api, rtc


def events_by_participant(log_path: Path, room: str) -> tuple[dict[str, list[dict]], list[dict]]:
    samples: dict[str, list[dict]] = defaultdict(list)
    statuses: list[dict] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            message = json.loads(line).get("message", "")
        except json.JSONDecodeError:
            continue
        if room not in message or not message.startswith(("emotion.samples", "ml.status")):
            continue
        event = json.loads(message.split(" ", 2)[2])
        if event["type"] == "ml.status":
            statuses.append(event["payload"])
        else:
            samples[event["payload"]["participant_id"]].append(event["payload"])
    return samples, statuses


def kill_agent() -> int:
    killed = 0
    # Только сам воркер (emotion-agent.exe / …/emotion-agent), а не оболочки, в командной строке которых он упомянут.
    for proc in psutil.process_iter(["name", "cmdline"]):
        argv0 = Path((proc.info.get("cmdline") or [""])[0]).name.lower()
        if proc.info.get("name", "").lower().startswith("emotion-agent") or argv0 in (
            "emotion-agent",
            "emotion-agent.exe",
        ):
            for child in proc.children(recursive=True):
                child.kill()
            proc.kill()
            killed += 1
    return killed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--agent-log", required=True)
    parser.add_argument("--seconds", type=float, default=40)
    parser.add_argument("--kill-agent", action="store_true")
    args = parser.parse_args()
    face = cv2.cvtColor(cv2.imread(args.image), cv2.COLOR_BGR2RGB)
    blank = np.full_like(face, 90)  # Вера: камера включена, лица нет

    room_name = str(uuid.uuid4())
    people = {"Анна": (uuid.uuid4(), "granted", face), "Борис": (uuid.uuid4(), "denied", face),
              "Вера": (uuid.uuid4(), "granted", blank)}  # fmt: skip
    lkapi = api.LiveKitAPI(URL.replace("ws", "http", 1), KEY, SECRET)
    stop = asyncio.Event()
    rooms: dict[str, rtc.Room] = {}
    tasks = []
    for name, (pid, consent, image) in people.items():
        room = rtc.Room()
        await room.connect(URL, token(room_name, f"p_{pid}", name, consent))
        rooms[name] = room
        tasks.append(asyncio.create_task(publish_camera(room, image, stop)))
        await asyncio.sleep(0.5)
    await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name="emotion-agent", room=room_name, metadata=json.dumps({"fps": 3}))
    )
    t = args.seconds
    await asyncio.sleep(0.25 * t)
    # Камеру выключает сам участник (как кнопка в браузере): включение со стороны сервера LiveKit запрещено.
    camera = next(iter(rooms["Анна"].local_participant.track_publications.values())).track
    camera.mute()
    await asyncio.sleep(4)
    camera.unmute()
    killed = 0
    if args.kill_agent:
        await asyncio.sleep(0.1 * t)
        killed = kill_agent()
    else:
        await asyncio.sleep(0.6 * t - 0.25 * t - 4)
        await lkapi.room.update_participant(
            api.UpdateParticipantRequest(
                room=room_name, identity=f"p_{people['Анна'][0]}", attributes={"vks.consent": "revoked"}
            )
        )
    await asyncio.sleep(0.4 * t)
    connected = {name: room.connection_state == rtc.ConnectionState.CONN_CONNECTED for name, room in rooms.items()}
    stop.set()
    await asyncio.gather(*tasks)
    for room in rooms.values():
        await room.disconnect()
    await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lkapi.aclose()
    await asyncio.sleep(2)

    samples, statuses = events_by_participant(Path(args.agent_log), room_name)
    anna, boris, vera = (samples.get(str(people[n][0]), []) for n in ("Анна", "Борис", "Вера"))
    anna_states = [s["state"] for s in anna]
    checks = {
        "Агент вошел по диспетчеризации, ml.status active": any(s["state"] == "active" for s in statuses),
        "Анна (согласие): отсчеты analyzing с вероятностями": any(
            s["state"] == "analyzing" and s["probs"] for s in anna
        ),
        "Анна: внимание передается в отсчете": any(s.get("attention") for s in anna),
        "Борис (отказ): только no_consent, без вероятностей": bool(boris)
        and all(s["state"] == "no_consent" and s["probs"] is None for s in boris),
        "Вера (нет лица): no_face, не чаще 1 раза в секунду": bool(vera)
        and all(s["state"] == "no_face" for s in vera)
        and len(vera) <= t + 2,
        "Анна выключила камеру: camera_off, затем снова analyzing": "camera_off" in anna_states
        and "analyzing" in anna_states[anna_states.index("camera_off") :],
    }
    if args.kill_agent:
        checks["Отказ ML: процессы агента завершены"] = killed > 0
        checks["Отказ ML: видеосвязь у всех участников продолжилась"] = all(connected.values())
    else:
        checks["Отзыв согласия: последний отсчет Анны – no_consent"] = (
            bool(anna_states) and anna_states[-1] == "no_consent"
        )
        checks["Встреча удалена: ml.status stopped"] = any(s["state"] == "stopped" for s in statuses)
    result = {
        "room": room_name,
        "samples": {n: dict(Counter(s["state"] for s in samples.get(str(people[n][0]), []))) for n in people},
        "checks": {k: "пройдено" if v else "НЕ ПРОЙДЕНО" for k, v in checks.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
