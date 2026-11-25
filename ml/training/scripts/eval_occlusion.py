"""Устойчивость модели эмоций к очкам и бороде: тест FER-2013 чистый и с синтетическими очками / бородой.

Наборы (fer_training.occlusions.OCCLUSION_SETS) детерминированы – одинаковы для всех моделей. Модель – ONNX по
карточке (как в сервисе, без отражения). Дополнительно – подмножества теста с настоящими очками и бородой,
найденные детектором признаков (models/attributes): в FER-2013 такие лица есть, но их мало.

Запуск из ml/training:  uv run python scripts/eval_occlusion.py --card ../models/emotion/model_card.json [--card …]
Результат – results/occlusion_<model_version>.json и таблица в консоли.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from emotion_service.attributes import AttributeDetector, attribute_crop
from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.labels import LABELS
from emotion_service.preprocessing import FaceBox, to_model_batch
from sklearn.metrics import f1_score

from fer_training.data import load_fer2013
from fer_training.occlusions import OCCLUSION_SETS, occlude_set

MODELS = Path(__file__).absolute().parents[2] / "models"


def predict(classifier: OnnxEmotionClassifier, images: np.ndarray) -> np.ndarray:
    batch = to_model_batch(list(images))
    return np.concatenate([classifier.predict(batch[i : i + 64]) for i in range(0, len(batch), 64)])


def scores(labels: np.ndarray, probs: np.ndarray) -> dict[str, object]:
    preds = probs.argmax(1)
    return {
        "n": int(len(labels)),
        "accuracy": round(float((preds == labels).mean()), 4),
        "macro_f1": round(float(f1_score(labels, preds, average="macro", labels=range(len(LABELS)))), 4),
        "recall": {name: round(float((preds[labels == i] == i).mean()), 3) for i, name in enumerate(LABELS)},
    }


def real_attributes(images: np.ndarray) -> np.ndarray:
    """(N, 2) – настоящие очки / борода на изображениях FER по детектору признаков (вероятность ≥ порога)."""
    detector = AttributeDetector(MODELS / "attributes" / "attributes_card.json", threads=4)
    crops = []
    for gray in images:
        rgb = np.repeat(cv2.resize(gray, (192, 192), interpolation=cv2.INTER_CUBIC)[:, :, None], 3, axis=2)
        # Рамка YuNet относительно кадрирования FER (calibrate_crop.py): x0 0,096, y0 −0,013, w 0,814, h 1,03.
        crops.append(attribute_crop(rgb, FaceBox(192 * 0.096, -192 * 0.013, 192 * 0.814, 192 * 1.03, 1.0)))
    batch = np.stack(crops)
    probs = np.concatenate([detector.predict(batch[i : i + 128]) for i in range(0, len(batch), 128)])
    return probs >= detector.thresholds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", action="append", required=True)
    args = parser.parse_args()

    fer = load_fer2013(Path("data/fer2013"))
    images = np.concatenate([fer["public_test"].images, fer["private_test"].images])
    labels = np.concatenate([fer["public_test"].labels, fer["private_test"].labels])
    points = np.concatenate([fer["public_test"].landmarks, fer["private_test"].landmarks])
    sets = {"clean": images} | {name: occlude_set(images, points, name, seed=7) for name in OCCLUSION_SETS}
    real = real_attributes(images)
    print(f"Настоящие очки в тесте: {real[:, 0].sum()}, борода: {real[:, 1].sum()} из {len(images)}")

    Path("results").mkdir(exist_ok=True)
    for card in args.card:
        classifier = OnnxEmotionClassifier(card, threads=8)
        report: dict[str, object] = {}
        clean = None
        for name, data in sets.items():
            probs = predict(classifier, data)
            report[name] = scores(labels, probs)
            if name == "clean":
                clean = probs
        if clean is None:
            raise RuntimeError("Нет чистого набора")
        report["real_glasses"] = scores(labels[real[:, 0]], clean[real[:, 0]])
        report["real_beard"] = scores(labels[real[:, 1]], clean[real[:, 1]])
        report["real_none"] = scores(labels[~real.any(1)], clean[~real.any(1)])
        version = classifier.model_version
        Path(f"results/occlusion_{version.replace('@', '_')}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
        )
        print(f"\n{version}")
        for name, r in report.items():
            if not isinstance(r, dict):
                continue
            recall = r["recall"]
            print(
                f"  {name:16s} n={r['n']:5d} acc={r['accuracy']:.4f} F1={r['macro_f1']:.4f} "
                f"surprise={recall['surprise']:.3f} fear={recall['fear']:.3f} happy={recall['happy']:.3f}"
            )


if __name__ == "__main__":
    main()
