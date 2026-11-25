"""EMO-44 (в отчете спринта 3 – EMO-42): сравнение детекторов лиц YuNet и MediaPipe BlazeFace на CPU.

Тестовые кадры – синтетические «кадры ВКС» 640×360 и 1280×720: лицо из теста FER-2013 (увеличенное до 48–200 px)
на размытом шумовом фоне. Это прокси: лица FER – уже кропы низкого качества, поэтому доля найденных лиц здесь
ниже, чем на живом видео, но она одинаково сложна для обоих детекторов. Скорость от содержимого кадра почти не
зависит. Проверка на записях встреч команды – в EMO-63/65.

Запуск из ml/training:  uv run python scripts/bench_face_detectors.py --frames 300
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import cv2
import numpy as np
from emotion_service.detection import YuNetDetector
from emotion_service.preprocessing import FaceBox

from fer_training.data import load_fer2013

MODELS = Path(__file__).absolute().parents[2] / "models"


class MediaPipeDetector:
    def __init__(self, model_path: Path, min_confidence: float = 0.5) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            min_detection_confidence=min_confidence,
        )
        self._detector = vision.FaceDetector.create_from_options(options)

    def detect(self, image: np.ndarray) -> list[FaceBox]:
        result = self._detector.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=image))
        boxes = []
        for det in result.detections:
            b = det.bounding_box
            boxes.append(FaceBox(b.origin_x, b.origin_y, b.width, b.height, det.categories[0].score))
        return sorted(boxes, key=lambda f: f.area, reverse=True)


def make_frames(n: int, size: tuple[int, int], seed: int = 0) -> list[tuple[np.ndarray, tuple[int, int, int, int]]]:
    """(RGB-кадр, рамка лица x, y, w, h)."""
    rng = np.random.default_rng(seed)
    fer = load_fer2013(Path("data/fer2013"))["private_test"]
    width, height = size
    frames = []
    for i in rng.choice(len(fer), n, replace=False):
        noise = rng.integers(0, 255, (height // 8, width // 8, 3), dtype=np.uint8)
        frame = cv2.GaussianBlur(cv2.resize(noise, (width, height), interpolation=cv2.INTER_LINEAR), (0, 0), 6)
        side = int(rng.integers(max(48, height // 7), int(height * 0.55)))
        face = cv2.resize(fer.images[i], (side, side), interpolation=cv2.INTER_CUBIC)
        x, y = int(rng.integers(0, width - side)), int(rng.integers(0, height - side))
        frame[y : y + side, x : x + side] = face[:, :, None]
        frames.append((frame, (x, y, side, side)))
    return frames


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0.0, min(ax2, bx2) - max(a[0], b[0])), max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def run(detector: object, frames: list[tuple[np.ndarray, tuple[int, int, int, int]]]) -> dict[str, float]:
    for frame, _ in frames[:10]:
        detector.detect(frame)  # type: ignore[attr-defined]
    timings, hits, false_pos = [], 0, 0
    for frame, truth in frames:
        start = time.perf_counter()
        faces = detector.detect(frame)  # type: ignore[attr-defined]
        timings.append((time.perf_counter() - start) * 1000)
        matched = [f for f in faces if iou((f.x, f.y, f.w, f.h), truth) >= 0.3]
        hits += bool(matched)
        false_pos += len(faces) - len(matched[:1])
    return {
        "ms_median": round(float(np.median(timings)), 2),
        "ms_p95": round(float(np.percentile(timings, 95)), 2),
        "recall": round(hits / len(frames), 4),
        "false_positives_per_frame": round(false_pos / len(frames), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--out", default="results/face_detectors.json")
    args = parser.parse_args()
    cv2.setNumThreads(args.threads)

    detectors = {
        "YuNet 2023mar (OpenCV)": lambda: YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx"),
        "MediaPipe BlazeFace short-range": lambda: MediaPipeDetector(
            MODELS / "mediapipe" / "blaze_face_short_range.tflite"
        ),
    }
    report: dict[str, object] = {
        "cpu": platform.processor(),
        "opencv_threads": args.threads,
        "frames": args.frames,
        "results": {},
    }
    for size in ((640, 360), (1280, 720)):
        frames = make_frames(args.frames, size)
        for name, factory in detectors.items():
            result = run(factory(), frames)
            report["results"][f"{name} @ {size[0]}x{size[1]}"] = result  # type: ignore[index]
            print(f"{name:34s} {size[0]}x{size[1]}: {result}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    main()
