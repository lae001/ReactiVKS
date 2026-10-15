"""Живая демонстрация конвейера на веб-камере: http://localhost:8765

Браузер берет кадры с камеры (getUserMedia) и отправляет их по WebSocket; сервер прогоняет каждый кадр через тот же
конвейер, что и агент (YuNet → кроп 48×48 → ONNX-модель → EMA; внимание по позе головы), и возвращает результат: рамку и
опорные точки лица, кроп, который видит модель, сырые и сглаженные вероятности, задержки. Кадры не сохраняются.

    python scripts/live_demo.py --card <каталог модели>/model_card.json [--port 8765]
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np
from aiohttp import WSMsgType, web

from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.detection import YuNetDetector
from emotion_service.events import attention_payload
from emotion_service.fusion import BlendshapeHead
from emotion_service.landmarks import FaceMeshAnalyzer
from emotion_service.pipeline import EmotionPipeline
from emotion_service.smoothing import TemporalSmoother

HERE = Path(__file__).absolute().parent
MODELS = HERE.parents[1] / "models"
log = logging.getLogger("live_demo")


def build_pipeline(card: Path, alpha: float) -> EmotionPipeline:
    mesh_model = MODELS / "mediapipe" / "face_landmarker.task"
    head_path = card.parent / "blendshape_head.json"
    return EmotionPipeline(
        YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx"),
        OnnxEmotionClassifier(card, threads=2),
        TemporalSmoother(alpha=alpha),
        mesh=FaceMeshAnalyzer(mesh_model) if mesh_model.exists() else None,
        blendshape_head=BlendshapeHead.load(head_path) if head_path.exists() else None,
    )


# Мимические коэффициенты, которые показывает страница: (название, коэффициенты MediaPipe для усреднения).
EXPRESSIONS = {
    "Брови вверх (внутр.)": ("browInnerUp",),
    "Брови вверх (внеш.)": ("browOuterUpLeft", "browOuterUpRight"),
    "Брови сведены": ("browDownLeft", "browDownRight"),
    "Глаза широко": ("eyeWideLeft", "eyeWideRight"),
    "Прищур": ("eyeSquintLeft", "eyeSquintRight"),
    "Рот открыт": ("jawOpen",),
    "Улыбка": ("mouthSmileLeft", "mouthSmileRight"),
    "Уголки рта вниз": ("mouthFrownLeft", "mouthFrownRight"),
    "Нос сморщен": ("noseSneerLeft", "noseSneerRight"),
}


def encode_png(image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", image)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode() if ok else ""


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(HERE / "live_demo.html")


async def info(request: web.Request) -> web.Response:
    pipeline: EmotionPipeline = request.app["pipeline"]
    card = request.app["card"]
    return web.json_response(
        {
            "model_version": pipeline.classifier.model_version,
            "labels": list(pipeline.classifier.labels),
            "metrics": card.get("metrics", {}),
            "alpha": pipeline.smoother.alpha,
            "mesh": pipeline.mesh is not None,
            "fusion_weight": pipeline.blendshape_head.weight if pipeline.blendshape_head else None,
        }
    )


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(max_msg_size=8 * 1024 * 1024)
    await ws.prepare(request)
    # Свое сглаживание на каждое подключение: новая вкладка начинает с чистого состояния.
    pipeline = build_pipeline(request.app["card_path"], request.app["alpha"])
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            command = json.loads(msg.data).get("cmd")
            if command == "calibrate":
                pipeline.calibrator.start("me")
            elif command == "reset_calibration":
                pipeline.calibrator.reset("me")
                pipeline.smoother.reset("me")
            continue
        if msg.type != WSMsgType.BINARY:
            continue
        started = time.perf_counter()
        bgr = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        decoded = time.perf_counter()
        (result,) = pipeline.process([("me", rgb)], time.monotonic())
        processed = time.perf_counter()
        payload: dict[str, object] = {
            "state": result.state,
            "frame": [rgb.shape[1], rgb.shape[0]],
            "timing_ms": {
                "decode": round((decoded - started) * 1000, 1),
                "pipeline": round((processed - decoded) * 1000, 1),
            },
        }
        status = pipeline.calibrator.status("me", time.monotonic())
        payload["calibration"] = {"state": status.state, "progress": round(status.progress, 2)}
        if result.attention is not None:
            payload["attention"] = attention_payload(result.attention)
        if result.state == "analyzing" and result.face is not None and result.crop is not None:
            face, k = result.face, result.scale
            payload.update(
                box=[face.x * k, face.y * k, face.w * k, face.h * k],
                score=round(face.score, 3),
                landmarks=(face.landmarks * k).round(1).tolist() if face.landmarks is not None else None,
                probs=result.probs,
                raw_probs=result.raw_probs,
                dominant=result.dominant,
                raw_dominant=result.raw_dominant,
                confidence=result.confidence,
                face_box_area=result.face_box_area,
                crop=encode_png(result.crop),
                cnn_probs=result.cnn_probs,
                uncalibrated_probs=result.uncalibrated_probs,
            )
            if result.mesh is not None:
                mesh = result.mesh
                payload["mesh"] = {
                    "points": (mesh.points[:, :2] * k).round(1).tolist(),
                    "expressions": {
                        name: round(sum(mesh.blendshapes.get(key, 0.0) for key in keys) / len(keys), 3)
                        for name, keys in EXPRESSIONS.items()
                    },
                    "yaw": round(mesh.yaw_deg, 1),
                    "pitch": round(mesh.pitch_deg, 1),
                    "roll": round(mesh.roll_deg, 1),
                }
        await ws.send_str(json.dumps(payload))
    return ws


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True, help="model_card.json (ONNX-файл – рядом)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--alpha", type=float, default=0.4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    card_path = Path(args.card)
    app = web.Application()
    app["card_path"] = card_path
    app["card"] = json.loads(card_path.read_text(encoding="utf-8"))
    app["alpha"] = args.alpha
    app["pipeline"] = build_pipeline(card_path, args.alpha)
    app.add_routes([web.get("/", index), web.get("/info", info), web.get("/ws", ws_handler)])
    # Только localhost: камера и лицо не уходят с машины.
    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
