"""Итоговые метрики системы для отчета о качестве (EMO-74): тест FER-2013, конвейер как в сервисе.

Маршрутизация – по настоящему детектору очков и бороды (models/attributes), мимика – коэффициенты чистого теста
(extract_blendshapes.py) с отключением закрытых зон и весом условия из blendshape_head.json устойчивой модели.
Результат – results/final_metrics.json и docs/ml/img/confusion_final.png.

Запуск из ml/training:  uv run python scripts/final_report_metrics.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emotion_service.classifier import OnnxEmotionClassifier, RoutedClassifier
from emotion_service.fusion import BlendshapeHead
from emotion_service.labels import LABELS
from emotion_service.preprocessing import to_model_batch
from eval_occlusion import real_attributes
from sklearn.metrics import precision_recall_fscore_support

from fer_training.data import FER_SPLITS, image_hashes, load_fer2013
from fer_training.metrics import compute_metrics, plot_confusion

MODELS = Path(__file__).absolute().parents[2] / "models"
TITLES = ("Гнев", "Отвращение", "Страх", "Радость", "Грусть", "Удивление", "Нейтральное")


def main() -> None:
    fer = load_fer2013(Path("data/fer2013"))
    images = np.concatenate([fer["public_test"].images, fer["private_test"].images])
    labels = np.concatenate([fer["public_test"].labels, fer["private_test"].labels])
    attrs = real_attributes(images)
    occluded = attrs.any(1)

    routed = RoutedClassifier(
        OnnxEmotionClassifier(MODELS / "emotion" / "model_card.json", threads=8),
        OnnxEmotionClassifier(MODELS / "emotion-robust" / "model_card.json", threads=8),
    )
    batch = to_model_batch(list(images))
    cnn = np.concatenate([routed.predict(batch[i : i + 64], occluded[i : i + 64]) for i in range(0, len(batch), 64)])

    raw = np.load("data/fer2013/blendshapes.npz")
    table = {h: r for sp in FER_SPLITS for h, r in zip(image_hashes(fer[sp].images), raw[sp], strict=True)}
    head = BlendshapeHead.load(MODELS / "emotion-robust" / "blendshape_head.json")
    final = cnn.copy()
    for i, digest in enumerate(image_hashes(images)):
        features = table.get(digest)
        if features is not None and not np.isnan(features[0]):
            names = tuple(n for n, flag in zip(("glasses", "beard"), attrs[i], strict=True) if flag)
            final[i] = head.fuse_with_attributes(cnn[i], features, names)

    report = {}
    for name, probs in (("cnn_routed", cnn), ("final", final)):
        metrics = compute_metrics(labels, probs)
        p, r, f, s = precision_recall_fscore_support(
            labels, probs.argmax(1), labels=range(len(LABELS)), zero_division=0
        )
        metrics["per_class"] = {
            LABELS[i]: {
                "precision": round(float(p[i]), 3),
                "recall": round(float(r[i]), 3),
                "f1": round(float(f[i]), 3),
                "support": int(s[i]),
            }
            for i in range(len(LABELS))
        }
        report[name] = metrics
        print(name, round(metrics["accuracy"], 4), round(metrics["macro_f1"], 4))
    report["routing"] = {"faces_with_glasses_or_beard": int(occluded.sum()), "n": int(len(labels))}
    Path("results").mkdir(exist_ok=True)
    Path("results/final_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    out = Path(__file__).absolute().parents[3] / "docs" / "ml" / "img"
    out.mkdir(parents=True, exist_ok=True)
    final_metrics = report["final"]
    plot_confusion(
        final_metrics["confusion"],
        out / "confusion_final.png",
        f"Тест FER-2013, итоговая система: accuracy {final_metrics['accuracy']:.3f}",
    )
    print(json.dumps(final_metrics["per_class"], ensure_ascii=False))


if __name__ == "__main__":
    main()
