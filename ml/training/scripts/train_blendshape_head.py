"""Голова эмоций по мимике: логистическая регрессия по 52 коэффициентам MediaPipe + подбор веса смешивания с CNN.

Признаки – data/fer2013/blendshapes.npz (scripts/extract_blendshapes.py), сплиты – те же, что у CNN
(fer_training.data.build_splits); строки сопоставляются по хешу изображения. C регрессии и вес смешивания
выбираются по accuracy на валидации; тест – только для итоговых чисел. Результат – blendshape_head.json рядом с
карточкой модели; сервис подхватывает его автоматически (emotion_service.fusion).

Запуск из ml/training:  uv run python scripts/train_blendshape_head.py --card runs/<запуск>/model_card.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.fusion import fuse
from emotion_service.labels import LABELS
from emotion_service.landmarks import BLENDSHAPE_NAMES
from emotion_service.preprocessing import to_model_batch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

from fer_training.config import DataConfig
from fer_training.data import FER_SPLITS, ImageSet, build_splits, image_hashes, load_fer2013

SURPRISE = LABELS.index("surprise")


def features_for(data: ImageSet, table: dict[str, np.ndarray]) -> np.ndarray:
    nan = np.full(len(BLENDSHAPE_NAMES), np.nan, np.float32)
    return np.stack([table.get(h, nan) for h in image_hashes(data.images)])


def score(labels: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    preds = probs.argmax(1)
    return {
        "accuracy": round(float(accuracy_score(labels, preds)), 4),
        "macro_f1": round(float(f1_score(labels, preds, average="macro")), 4),
        "surprise_recall": round(float((preds[labels == SURPRISE] == SURPRISE).mean()), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--ferplus", help="метки FER+ (data/ferplus/fer2013new.csv) вместо исходных меток FER-2013")
    args = parser.parse_args()
    card = Path(args.card)

    raw = np.load("data/fer2013/blendshapes.npz")
    fer = load_fer2013(Path("data/fer2013"))
    table: dict[str, np.ndarray] = {}
    for split in FER_SPLITS:
        for digest, row in zip(image_hashes(fer[split].images), raw[split], strict=True):
            if not np.isnan(row[0]):
                table[digest] = row

    splits = build_splits(DataConfig(ferplus=args.ferplus), 42, Path.cwd())
    sets = {"train": splits.train, "val": splits.val, "test": splits.tests["ferplus" if args.ferplus else "fer2013"]}
    feats = {name: features_for(data, table) for name, data in sets.items()}
    found = {name: ~np.isnan(f[:, 0]) for name, f in feats.items()}
    for name in sets:
        print(f"{name}: сетка построена для {found[name].mean():.3f}")

    x_train, y_train = feats["train"][found["train"]], sets["train"].labels[found["train"]]
    mean, std = x_train.mean(0), x_train.std(0) + 1e-6

    def head_probs(model: LogisticRegression, name: str) -> np.ndarray:
        probs = np.full((len(sets[name]), len(LABELS)), 1 / len(LABELS), np.float32)
        probs[found[name]] = model.predict_proba((feats[name][found[name]] - mean) / std)
        return probs

    best_c, best_model, best_acc = 0.0, None, -1.0
    for c in (0.01, 0.1, 1.0, 10.0):
        model = LogisticRegression(C=c, max_iter=2000).fit((x_train - mean) / std, y_train)
        val = sets["val"].labels[found["val"]]
        acc = accuracy_score(val, model.predict((feats["val"][found["val"]] - mean) / std))
        print(f"C={c}: val acc головы {acc:.4f}")
        if acc > best_acc:
            best_c, best_model, best_acc = c, model, acc
    if best_model is None:
        raise RuntimeError("Голова не обучена")

    classifier = OnnxEmotionClassifier(card, threads=4)

    def cnn_probs(data: ImageSet) -> np.ndarray:
        batch = to_model_batch(list(data.images))
        return np.concatenate([classifier.predict(batch[i : i + 64]) for i in range(0, len(batch), 64)])

    cnn = {name: cnn_probs(sets[name]) for name in ("val", "test")}
    head = {name: head_probs(best_model, name) for name in ("val", "test")}

    def fused(name: str, weight: float) -> np.ndarray:
        out = cnn[name].copy()
        mask = found[name]
        out[mask] = fuse(cnn[name][mask], head[name][mask], weight)
        return out

    weights = [round(w, 2) for w in np.arange(0, 0.75, 0.05)]
    val_acc = {w: score(sets["val"].labels, fused("val", w))["accuracy"] for w in weights}
    best_w = max(val_acc, key=lambda w: val_acc[w])
    print("val accuracy по весу:", val_acc)

    report = {
        "C": best_c,
        "fusion_weight": best_w,
        "coverage": {name: round(float(found[name].mean()), 4) for name in sets},
        "val": {
            "cnn": score(sets["val"].labels, cnn["val"]),
            "head": score(sets["val"].labels, head["val"]),
            "fused": score(sets["val"].labels, fused("val", best_w)),
        },
        "test": {
            "cnn": score(sets["test"].labels, cnn["test"]),
            "head": score(sets["test"].labels, head["test"]),
            "fused": score(sets["test"].labels, fused("test", best_w)),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = {
        "labels": list(LABELS),
        "features": list(BLENDSHAPE_NAMES),
        "mean": mean.tolist(),
        "std": std.tolist(),
        "coef": best_model.coef_.tolist(),
        "intercept": best_model.intercept_.tolist(),
        "fusion_weight": best_w,
        "report": report,
    }
    (card.parent / "blendshape_head.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
