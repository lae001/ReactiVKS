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
import re
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from aiohttp import WSMsgType, web

from emotion_service.attributes import AttributeDetector
from emotion_service.calibration import NeutralCalibrator
from emotion_service.classifier import OnnxEmotionClassifier, RoutedClassifier
from emotion_service.detection import YuNetDetector
from emotion_service.events import attention_payload, behavior_model
from emotion_service.fusion import OCCLUDED_ZONES, BlendshapeHead
from emotion_service.labels import LABELS
from emotion_service.landmarks import FaceMeshAnalyzer
from emotion_service.pipeline import EmotionPipeline, FaceResult
from emotion_service.smoothing import TemporalSmoother

HERE = Path(__file__).absolute().parent
MODELS = HERE.parents[1] / "models"
log = logging.getLogger("live_demo")


def build_pipeline(card: Path, alpha: float) -> EmotionPipeline:
    mesh_model = MODELS / "mediapipe" / "face_landmarker.task"
    attributes_card = MODELS / "attributes" / "attributes_card.json"
    robust_card = MODELS / "emotion-robust" / "model_card.json"
    classifier: OnnxEmotionClassifier | RoutedClassifier = OnnxEmotionClassifier(card, threads=2)
    head_path = card.parent / "blendshape_head.json"
    if robust_card.exists() and robust_card.resolve() != card.resolve():
        # Без очков и бороды – ансамбль базовой и устойчивой моделей, с ними – устойчивая (experiments.md, §9).
        classifier = RoutedClassifier(classifier, OnnxEmotionClassifier(robust_card, threads=2))
        head_path = robust_card.parent / "blendshape_head.json"
    return EmotionPipeline(
        YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx"),
        classifier,
        TemporalSmoother(alpha=alpha),
        mesh=FaceMeshAnalyzer(mesh_model) if mesh_model.exists() else None,
        blendshape_head=BlendshapeHead.load(head_path) if head_path.exists() else None,
        attribute_detector=AttributeDetector(attributes_card) if attributes_card.exists() else None,
        calibrator=NeutralCalibrator(auto=True),  # калибруется сам по 5 с спокойного лица; кнопка – вручную
    )


PERSON_CODE = re.compile(r"^[A-Za-z0-9_]{1,16}$")  # «-» – разделитель в имени файла
LEGACY_PERSON = "P01"  # записи до появления кода участника – автор выборки
CONSENT_NOTICE = "own-dataset-v1"
TARGET_PEOPLE = 10
TARGET_PER_EMOTION = 30


class Recorder:
    """Сбор собственной выборки (EMO-92): кадры с меткой «какую эмоцию я сейчас изображаю».

    Сохраняются только входы моделей – кроп 48×48 (PNG), коэффициенты мимики и вероятности очков / бороды
    (JSON); полные кадры не пишутся. Папка – --record-dir, по умолчанию ml/training/data/own (в .gitignore):
    own/<эмоция>/<код участника>-<время>.png|json. Участник – анонимный код (P01, P02 …), не имя; запись
    возможна только после его согласия (own/consent.jsonl), по коду его данные удаляются целиком.
    Цель – не меньше TARGET_PEOPLE человек по TARGET_PER_EMOTION кадров каждой эмоции. Оценка и дообучение –
    ml/training/scripts/eval_own.py и finetune_own.py (разбиение по людям).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.label: str | None = None
        self.person = LEGACY_PERSON
        self.until = 0.0
        self.saved: dict[str, int] = {}
        self.recording_id = ""

    def consent(self, person: str) -> bool:
        if not PERSON_CODE.match(person):
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"person": person, "notice": CONSENT_NOTICE, "at": datetime.now().astimezone().isoformat()}
        with (self.root / "consent.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True

    def consented(self) -> set[str]:
        path = self.root / "consent.jsonl"
        if not path.exists():
            return set()
        return {json.loads(line)["person"] for line in path.read_text(encoding="utf-8").splitlines() if line}

    def start(self, label: str, seconds: float, person: str) -> bool:
        if label not in LABELS or not PERSON_CODE.match(person) or person not in self.consented():
            return False
        self.label, self.person, self.until = label, person, time.monotonic() + seconds
        self.recording_id = f"{person}-" + datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        return True

    @staticmethod
    def _person_of(png: Path) -> str:
        head = png.stem.split("-", 1)[0]
        return head if PERSON_CODE.match(head) and not head.isdigit() else LEGACY_PERSON

    def stats(self) -> dict[str, object]:
        counts: dict[str, dict[str, int]] = {}
        for png in self.root.glob("*/*.png"):
            label = png.parent.name
            if label in LABELS:
                person = counts.setdefault(self._person_of(png), {})
                person[label] = person.get(label, 0) + 1
        complete = [p for p, c in counts.items() if all(c.get(label, 0) >= TARGET_PER_EMOTION for label in LABELS)]
        return {
            "people": counts,
            "complete": sorted(complete),
            "target_people": TARGET_PEOPLE,
            "target_per_emotion": TARGET_PER_EMOTION,
            "labels": list(LABELS),
        }

    def delete(self, person: str) -> int:
        """Удалить все кадры участника (отзыв согласия); запись о согласии помечается отозванной."""
        removed = 0
        for png in list(self.root.glob("*/*.png")):
            if self._person_of(png) == person:
                for path in (png, png.with_suffix(".json")):
                    if path.exists():
                        path.unlink()
                removed += 1
        if PERSON_CODE.match(person) and (self.root / "consent.jsonl").exists():
            lines = (self.root / "consent.jsonl").read_text(encoding="utf-8").splitlines()
            kept = [line for line in lines if line and json.loads(line)["person"] != person]
            (self.root / "consent.jsonl").write_text("".join(line + "\n" for line in kept), encoding="utf-8")
        return removed

    def maybe_save(self, result: FaceResult) -> None:
        if self.label is None:
            return
        if time.monotonic() > self.until:
            self.label = None
            return
        if result.state != "analyzing" or result.crop is None:
            return
        folder = self.root / self.label
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / (f"{self.person}-" + datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f"))
        cv2.imwrite(str(stem.with_suffix(".png")), result.crop)
        meta = {
            "label": self.label,
            "person": self.person,
            "recording_id": self.recording_id,
            "blendshapes": result.mesh.blendshapes if result.mesh is not None else None,
            "attributes": (
                {"glasses": result.attributes.glasses_prob, "beard": result.attributes.beard_prob}
                if result.attributes is not None
                else None
            ),
        }
        stem.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        self.saved[self.label] = self.saved.get(self.label, 0) + 1


class ProbeLog:
    """Проверка порогов речи и жестов на живой камере: страница ведет участника по шагам («молчите», «говорите»,
    «кивните», «покачайте головой», «отверните голову и верните»), сервер пишет по каждому кадру метку шага и сырые
    сигналы поведения. Файл – ml/training/data/probe/<время>.json (только числа, без изображений); разбор –
    ml/training/scripts/analyze_probe.py."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.step: str | None = None
        self.rows: list[dict[str, object]] = []

    def add(self, result: FaceResult) -> None:
        if self.step is None:
            return
        b, mesh = result.behavior, result.mesh
        self.rows.append(
            {
                "t": round(time.monotonic(), 3),
                "step": self.step,
                "face": result.state == "analyzing",
                "mouth_activity": b.mouth_activity if b else None,
                "speech": b.speech if b else None,
                "agreement": b.agreement if b else None,
                "nod_score": b.nod_score if b else None,
                "shake_score": b.shake_score if b else None,
                "yaw": round(mesh.yaw_deg, 2) if mesh else None,
                "pitch": round(mesh.pitch_deg, 2) if mesh else None,
            }
        )

    def save(self) -> str | None:
        if not self.rows:
            return None
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (datetime.now().astimezone().strftime("%Y%m%d-%H%M%S") + ".json")
        path.write_text(json.dumps(self.rows, ensure_ascii=False), "utf-8")
        self.rows = []
        return str(path)


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
    return web.FileResponse(HERE / "live_demo.html", headers={"Cache-Control": "no-store"})


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
    recorder: Recorder = request.app["recorder"]
    probe = ProbeLog(request.app["probe_dir"])
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            command = data.get("cmd")
            if command == "calibrate":
                pipeline.calibrator.start("me")
            elif command == "reset_calibration":
                pipeline.calibrator.reset("me")
                pipeline.smoother.reset("me")
            elif command == "mic":  # только флаг «микрофон включен», звук сюда не передается
                pipeline.mic["me"] = bool(data.get("on"))
            elif command == "consent":
                ok = recorder.consent(str(data.get("person", "")))
                await ws.send_str(json.dumps({"reply": "consent", "ok": ok, "dataset": recorder.stats()}))
            elif command == "record":
                ok = recorder.start(str(data.get("label")), float(data.get("seconds", 3)), str(data.get("person", "")))
                if not ok:
                    await ws.send_str(json.dumps({"reply": "record", "ok": False}))
            elif command == "dataset":
                await ws.send_str(json.dumps({"reply": "dataset", "dataset": recorder.stats()}))
            elif command == "delete_person":
                removed = recorder.delete(str(data.get("person", "")))
                await ws.send_str(json.dumps({"reply": "deleted", "removed": removed, "dataset": recorder.stats()}))
            elif command == "probe":
                probe.step = data.get("step")
            elif command == "probe_save":
                probe.step = None
                await ws.send_str(json.dumps({"reply": "probe_saved", "path": probe.save()}))
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
        recorder.maybe_save(result)
        probe.add(result)
        payload: dict[str, object] = {
            "state": result.state,
            "frame": [rgb.shape[1], rgb.shape[0]],
            "timing_ms": {
                "decode": round((decoded - started) * 1000, 1),
                "pipeline": round((processed - decoded) * 1000, 1),
            },
        }
        status = pipeline.calibrator.status("me", time.monotonic())
        payload["calibration"] = {"state": status.state, "progress": round(status.progress, 2), "auto": status.auto}
        if result.attention is not None:
            payload["attention"] = attention_payload(result.attention)
        payload["recording"] = {"label": recorder.label, "saved": recorder.saved}
        if result.attributes is not None:
            a = result.attributes
            payload["attributes"] = {
                "glasses": a.glasses,
                "beard": a.beard,
                "glasses_prob": a.glasses_prob,
                "beard_prob": a.beard_prob,
                "masked": [zone for name in a.occluded for zone in OCCLUDED_ZONES[name]],
            }
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
                groups=result.groups,
                dominant_group=result.dominant_group,
                behavior=(
                    behavior_model(result.behavior).model_dump(mode="json") if result.behavior is not None else None
                ),
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
    parser.add_argument("--record-dir", default=str(HERE.parents[1] / "training" / "data" / "own"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    card_path = Path(args.card)
    app = web.Application()
    app["card_path"] = card_path
    app["card"] = json.loads(card_path.read_text(encoding="utf-8"))
    app["alpha"] = args.alpha
    app["pipeline"] = build_pipeline(card_path, args.alpha)
    app["recorder"] = Recorder(Path(args.record_dir))
    app["probe_dir"] = Path(args.record_dir).parent / "probe"
    app.add_routes([web.get("/", index), web.get("/info", info), web.get("/ws", ws_handler)])
    # Только localhost: камера и лицо не уходят с машины.
    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
