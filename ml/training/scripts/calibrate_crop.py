"""Калибровка кропа лица: качество модели на пути агента (детектор YuNet → кроп) при разных отступах.

Изображения валидации FER-2013 увеличиваются до 200 px и помещаются в кадр 640×360; YuNet находит лицо, общий
препроцессинг вырезает кроп с заданным отступом, модель классифицирует. Сравнение с прямой подачей исходных
изображений показывает, насколько кроп агента отличается от кадрирования обучающих данных. Тест в подборе не
используется. Результат 14.10.2026 – в docstring emotion_service/preprocessing.py.

Запуск из ml/training:  uv run python scripts/calibrate_crop.py --card runs/<запуск>/model_card.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.detection import YuNetDetector
from emotion_service.labels import LABELS
from emotion_service.preprocessing import FaceBox, align_crop, to_model_batch

from fer_training.config import DataConfig
from fer_training.data import build_splits

MODELS = Path(__file__).absolute().parents[2] / "models"


def recall(preds: np.ndarray, labels: np.ndarray) -> str:
    per_class = " ".join(f"{name} {(preds[labels == i] == i).mean():.3f}" for i, name in enumerate(LABELS))
    return f"acc {(preds == labels).mean():.4f} | {per_class}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--samples", type=int, default=1500)
    parser.add_argument("--margins", type=float, nargs="+", default=[0.1, 0.0, -0.1, -0.15, -0.2])
    args = parser.parse_args()

    classifier = OnnxEmotionClassifier(args.card, threads=4)

    def predict(crops: list[np.ndarray]) -> np.ndarray:
        batch = to_model_batch(crops)
        return np.concatenate([classifier.predict(batch[i : i + 64]) for i in range(0, len(batch), 64)]).argmax(1)

    detector = YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx")
    val = build_splits(DataConfig(), 42, Path.cwd()).val
    index = np.random.default_rng(0).choice(len(val), min(args.samples, len(val)), replace=False)

    frames, faces, kept = [], [], []
    for i in index:
        frame = np.full((360, 640, 3), 60, np.uint8)
        frame[80:280, 220:420] = cv2.resize(val.images[i], (200, 200), interpolation=cv2.INTER_CUBIC)[:, :, None]
        found = detector.detect(frame)
        if found:
            frames.append(frame)
            faces.append(found[0])
            kept.append(i)
    labels = val.labels[kept]
    boxes = np.array([[f.x - 220, f.y - 80, f.w, f.h] for f in faces]) / 200
    print(f"Найдено лиц: {len(kept)} из {len(index)}")
    print("Рамка YuNet относительно кадрирования FER (x0, y0, w, h):", boxes.mean(0).round(3).tolist())
    print("Исходные изображения:", recall(predict([val.images[i] for i in kept]), labels))
    for margin in args.margins:
        for rotate in (False, True):
            crops = [align_crop(frame, FaceBox(f.x, f.y, f.w, f.h, f.score, f.landmarks), margin, rotate=rotate)
                     for frame, f in zip(frames, faces, strict=True)]  # fmt: skip
            print(f"отступ {margin:+.2f}, поворот {'да ' if rotate else 'нет'}:", recall(predict(crops), labels))


if __name__ == "__main__":
    main()
