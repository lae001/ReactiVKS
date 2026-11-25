"""Сравнение моделей на тестах FER-2013 (исходные метки) и FER+ (метки 10 разметчиков) – одни и те же изображения.

Запуск из ml/training:  uv run python scripts/eval_ferplus.py runs/<a>/best.pt runs/<b>/best.pt …
Результат – results/ferplus_compare.json: accuracy, macro-F1, полнота по классам и по 5 группам; без TTA, как в сервисе.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from emotion_service.labels import LABELS
from vks_contracts.ml_events import EMOTION_GROUPS

from fer_training.config import DataConfig
from fer_training.data import build_splits
from fer_training.metrics import compute_metrics
from fer_training.train import load_checkpoint, pick_device, predict

GROUP_OF = np.array([next(i for i, (_, m) in enumerate(EMOTION_GROUPS.items()) if label in m) for label in LABELS])


def group_accuracy(labels: np.ndarray, probs: np.ndarray) -> float:
    grouped = np.zeros((len(probs), len(EMOTION_GROUPS)))
    for k in range(len(LABELS)):
        grouped[:, GROUP_OF[k]] += probs[:, k]
    return float((grouped.argmax(1) == GROUP_OF[labels]).mean())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoints", nargs="+")
    args = parser.parse_args()
    device = pick_device()
    tests = build_splits(DataConfig(ferplus="data/ferplus/fer2013new.csv"), 42, Path.cwd()).tests
    report = {}
    for path in args.checkpoints:
        model, _ = load_checkpoint(Path(path), device)
        model = model.to(device)
        row = {}
        for name in ("fer2013", "ferplus"):
            data = tests[name]
            probs = predict(model, data, device, tta_flip=False)
            m = compute_metrics(data.labels, probs)
            row[name] = {
                "n": len(data),
                "accuracy": round(m["accuracy"], 4),
                "macro_f1": round(m["macro_f1"], 4),
                "groups_accuracy": round(group_accuracy(data.labels, probs), 4),
                "recall": {
                    LABELS[i]: round(float((probs.argmax(1)[data.labels == i] == i).mean()), 3) for i in range(7)
                },
            }
        report[path] = row
        brief = {k: {x: v[x] for x in ("accuracy", "macro_f1", "groups_accuracy")} for k, v in row.items()}
        print(path, json.dumps(brief))
    out = Path("results") / "ferplus_compare.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    main()
