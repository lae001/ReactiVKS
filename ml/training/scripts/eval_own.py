"""Оценка модели на собственной выборке команды (EMO-92): кадры, записанные в живой демонстрации с меткой.

Выборка – ml/training/data/own/<эмоция>/<время>.png (кроп 48×48) + .json (мимика, вероятности очков и бороды);
собирается кнопкой «Записать 3 с» в scripts/live_demo.py сервиса. Метка – эмоция, которую участник изображал
(самоотчет); при нескольких разметчиках метки сводятся заранее большинством голосов (docs/ml/ml-model.md).

Отчет: accuracy, macro-F1, полнота по классам, матрица ошибок – отдельно CNN, CNN + мимика с учетом очков и
бороды, и по условиям (без признаков / очки / борода). Кадры одной записи похожи друг на друга, поэтому
дополнительно считается accuracy по записям (голос большинства кадров одной 3-секундной записи).

Запуск из ml/training:  uv run python scripts/eval_own.py --card ../models/emotion/model_card.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from emotion_service.attributes import ATTRIBUTES
from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.fusion import BlendshapeHead
from emotion_service.labels import LABELS
from emotion_service.landmarks import BLENDSHAPE_NAMES
from emotion_service.preprocessing import to_model_batch
from sklearn.metrics import confusion_matrix, f1_score


def load(root: Path) -> list[dict[str, object]]:
    samples = []
    for png in sorted(root.glob("*/*.png")):
        meta = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
        samples.append({"crop": cv2.imread(str(png), cv2.IMREAD_GRAYSCALE), "stem": png.stem, **meta})
    return samples


def scores(labels: np.ndarray, preds: np.ndarray) -> dict[str, object]:
    present = sorted(set(labels.tolist()))
    return {
        "n": int(len(labels)),
        "accuracy": round(float((preds == labels).mean()), 4) if len(labels) else None,
        "macro_f1": round(float(f1_score(labels, preds, average="macro", labels=present)), 4) if len(labels) else None,
        "recall": {LABELS[i]: round(float((preds[labels == i] == i).mean()), 3) for i in present},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--data", default="data/own")
    parser.add_argument("--attributes-card", default="../models/attributes/attributes_card.json")
    args = parser.parse_args()

    samples = load(Path(args.data))
    if not samples:
        raise SystemExit(f"В {args.data} нет записей: соберите их в живой демонстрации («Записать 3 с»).")
    labels = np.array([LABELS.index(str(s["label"])) for s in samples])
    classifier = OnnxEmotionClassifier(args.card, threads=4)
    cnn = classifier.predict(to_model_batch([s["crop"] for s in samples]))  # type: ignore[misc]

    thresholds = json.loads(Path(args.attributes_card).read_text(encoding="utf-8"))["thresholds"]
    head_path = Path(args.card).parent / "blendshape_head.json"
    head = BlendshapeHead.load(head_path) if head_path.exists() else None
    fused = cnn.copy()
    conditions = []
    for i, s in enumerate(samples):
        attrs = s.get("attributes") or {}
        occluded = tuple(a for a in ATTRIBUTES if float(attrs.get(a, 0.0)) >= thresholds[a])  # type: ignore[union-attr]
        conditions.append("_".join(occluded) or "none")
        blend = s.get("blendshapes")
        if head is not None and isinstance(blend, dict):
            vector = np.array([blend.get(n, 0.0) for n in BLENDSHAPE_NAMES], np.float32)
            fused[i] = head.fuse_with_attributes(cnn[i], vector, occluded)

    report: dict[str, object] = {"model_version": classifier.model_version}
    for name, probs in (("cnn", cnn), ("cnn_mimic", fused)):
        preds = probs.argmax(1)
        part: dict[str, object] = {"all": scores(labels, preds)}
        for condition in sorted(set(conditions)):
            mask = np.array([c == condition for c in conditions])
            part[condition] = scores(labels[mask], preds[mask])
        # По записям: кадры одной 3-секундной записи – голос большинства.
        votes: dict[tuple[int, str], list[int]] = defaultdict(list)
        for s, label, pred in zip(samples, labels, preds, strict=True):
            votes[(int(label), str(s.get("recording_id") or s["stem"]))].append(int(pred))
        record_labels = np.array([k[0] for k in votes])
        record_preds = np.array([np.bincount(v, minlength=len(LABELS)).argmax() for v in votes.values()])
        part["by_recording"] = scores(record_labels, record_preds)
        part["confusion"] = confusion_matrix(labels, preds, labels=range(len(LABELS))).tolist()
        report[name] = part
    out = Path("results") / f"own_{classifier.model_version.replace('@', '_')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
