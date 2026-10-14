"""Спайк / e2e-проверка агента (EMO-45, в отчете спринта 4 – EMO-58) на локальном LiveKit.

Сценарий: в комнату входят два «участника» с видео 640×360 и 15 кадр/с – Анна с согласием и Борис без согласия;
агент диспетчеризуется как в meeting-service (CreateDispatch, metadata {"fps": 3}); через половину времени Анна
отзывает согласие (UpdateParticipant). Скрипт печатает, на какие дорожки подписан агент; события агента
(emotion.samples / ml.status) – в его журнале.

1. livekit-server --dev                                  (ключи devkey / secret, ws://localhost:7880)
2. emotion-agent start                                   (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
3. python scripts/e2e_livekit.py --image face.png --seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid

import cv2
import numpy as np
from livekit import api, rtc

URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")


def token(room: str, identity: str, name: str, consent: str) -> str:
    return (
        api.AccessToken(KEY, SECRET)
        .with_identity(identity)
        .with_name(name)
        .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .with_attributes({"vks.role": "guest", "vks.consent": consent, "vks.kind": "human"})
        .to_jwt()
    )


def make_frame(face: np.ndarray, t: int) -> np.ndarray:
    """Кадр 640×360: лицо на фоне, слегка смещается, как при живом видео."""
    frame = np.full((360, 640, 3), 60, dtype=np.uint8)
    side = 200
    face = cv2.resize(face, (side, side), interpolation=cv2.INTER_CUBIC)
    x = 220 + int(20 * np.sin(t / 15))
    frame[80 : 80 + side, x : x + side] = face
    return frame


async def publish_camera(room: rtc.Room, face: np.ndarray, stop: asyncio.Event) -> None:
    source = rtc.VideoSource(640, 360)
    track = rtc.LocalVideoTrack.create_video_track("camera", source)
    await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA))
    t = 0
    while not stop.is_set():
        rgba = cv2.cvtColor(make_frame(face, t), cv2.COLOR_RGB2RGBA)
        source.capture_frame(rtc.VideoFrame(640, 360, rtc.VideoBufferType.RGBA, rgba.tobytes()))
        t += 1
        await asyncio.sleep(1 / 15)


async def agents_in_room(lkapi: api.LiveKitAPI, room: str) -> list[str]:
    participants = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room))
    return [p.identity for p in participants.participants if p.attributes.get("vks.kind") == "agent"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="изображение лица (серое или цветное)")
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    face = cv2.cvtColor(cv2.imread(args.image), cv2.COLOR_BGR2RGB)

    room_name = str(uuid.uuid4())
    anna, boris = f"p_{uuid.uuid4()}", f"p_{uuid.uuid4()}"
    stop = asyncio.Event()
    lkapi = api.LiveKitAPI(URL.replace("ws", "http", 1), KEY, SECRET)
    rooms = []
    for identity, name, consent in ((anna, "Анна", "granted"), (boris, "Борис", "denied")):
        room = rtc.Room()
        await room.connect(URL, token(room_name, identity, name, consent))
        rooms.append(room)
    tasks = [asyncio.create_task(publish_camera(r, face, stop)) for r in rooms]
    print(json.dumps({"room": room_name, "anna": anna, "boris": boris}, ensure_ascii=False))

    await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name="emotion-agent", room=room_name, metadata=json.dumps({"fps": 3}))
    )
    half = args.seconds / 2
    await asyncio.sleep(half)
    print("агенты в комнате:", await agents_in_room(lkapi, room_name))
    print("Анна отзывает согласие")
    await lkapi.room.update_participant(
        api.UpdateParticipantRequest(room=room_name, identity=anna, attributes={"vks.consent": "revoked"})
    )
    await asyncio.sleep(half)

    stop.set()
    await asyncio.gather(*tasks)
    for room in rooms:
        await room.disconnect()
    await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lkapi.aclose()


if __name__ == "__main__":
    asyncio.run(main())
