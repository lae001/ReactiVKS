"""Дообучение модели эмоций на собственной выборке (EMO-92): веб-камера и офисный свет вместо лиц FER-2013.

Выборка – ml/training/data/own/<эмоция>/<код участника>-<время>.png (кроп 48×48, как в сервисе), собирается в живой
демонстрации («Сбор выборки»). Кадры одного человека очень похожи, поэтому качество проверяется только на людях,
которых модель при дообучении не видела: перекрестная проверка по людям (GroupKFold, участник целиком – в одном
фолде). Чтобы модель не забыла FER-2013, в каждый пакет подмешиваются его изображения (--fer-replay на один свой
кадр), а после дообучения точность на тесте FER-2013 сравнивается с исходной.

Правило принятия (записывается в отчет): точность на новых людях выше исходной не меньше чем на --min-gain, а на
тесте FER-2013 падает не больше чем на --max-fer-drop. Только тогда с --export выпускается новая версия модели.

Запуск из ml/training (нужно ≥ --min-people участников с полным набором эмоций):
    uv run python scripts/finetune_own.py
    uv run python scripts/finetune_own.py --export 1.2.0      # выпуск в ../models/emotion-own
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from emotion_service.labels import LABELS
from sklearn.model_selection import GroupKFold
from torch import nn
from torch.utils.data import ConcatDataset, DataLoader

from fer_training.augment import build_train_transform
from fer_training.data import FaceDataset, ImageSet, build_splits
from fer_training.train import load_checkpoint, pick_device, predict, seed_everything

log = logging.getLogger("finetune_own")
BASE_CHECKPOINT = "runs/ferplus/20261125-125737/best.pt"  # = models/emotion v1.2.0 (метки FER+)
PERSON = re.compile(r"^([A-Za-z0-9_]{1,16})-")
LEGACY_PERSON = "P01"  # записи до появления кода участника


def load_own(root: Path) -> tuple[ImageSet, np.ndarray, np.ndarray]:
    """Кропы, участники и записи (recording_id) собственной выборки."""
    images, labels, people, recordings = [], [], [], []
    for png in sorted(root.glob("*/*.png")):
        if png.parent.name not in LABELS:
            continue
        meta_path = png.with_suffix(".json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        match = PERSON.match(png.stem)
        person = meta.get("person") or (match.group(1) if match and not match.group(1).isdigit() else LEGACY_PERSON)
        image = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != (48, 48):
            continue
        images.append(image)
        labels.append(LABELS.index(png.parent.name))
        people.append(person)
        recordings.append(meta.get("recording_id") or png.stem)
    data = ImageSet(np.array(images, np.uint8).reshape(-1, 48, 48), np.array(labels, np.int64), "own")
    return data, np.array(people), np.array(recordings)


def accuracy(labels: np.ndarray, probs: np.ndarray) -> float:
    return float((probs.argmax(1) == labels).mean()) if len(labels) else float("nan")


def by_recording(labels: np.ndarray, probs: np.ndarray, recordings: np.ndarray) -> float:
    """Точность по записям: голос большинства кадров одной 3-секундной записи."""
    votes: dict[str, list[int]] = defaultdict(list)
    truth: dict[str, int] = {}
    for label, pred, rec in zip(labels, probs.argmax(1), recordings, strict=True):
        votes[rec].append(int(pred))
        truth[rec] = int(label)
    hits = [np.bincount(v, minlength=len(LABELS)).argmax() == truth[r] for r, v in votes.items()]
    return float(np.mean(hits)) if hits else float("nan")


def finetune(
    model: nn.Module, own: ImageSet, fer: ImageSet, args: argparse.Namespace, device: torch.device, level: str
) -> nn.Module:
    model = copy.deepcopy(model).to(device).train()
    rng = np.random.default_rng(args.seed)
    replay = fer.subset(rng.choice(len(fer), size=min(len(fer), len(own) * args.fer_replay), replace=False))
    transform = build_train_transform(level)  # type: ignore[arg-type]
    loader = DataLoader(
        ConcatDataset([FaceDataset(own, transform), FaceDataset(replay, transform)]),
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=len(own) + len(replay) > args.batch_size,
        num_workers=0,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    for _ in range(args.epochs):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(images)
            loss = criterion(logits.float(), labels)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    return model.eval()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=BASE_CHECKPOINT)
    parser.add_argument("--data", default="data/own")
    parser.add_argument("--min-people", type=int, default=10, help="минимум участников (по людям – честная оценка)")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--fer-replay", type=int, default=3, help="изображений FER-2013 на один свой кадр")
    parser.add_argument("--min-gain", type=float, default=0.02)
    parser.add_argument("--max-fer-drop", type=float, default=0.01)
    parser.add_argument("--export", metavar="VERSION", help="выпустить модель, если правило принятия выполнено")
    parser.add_argument("--out", default="../models/emotion-own")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed_everything(args.seed)
    base_dir = Path.cwd()

    own, people, recordings = load_own(Path(args.data))
    names = sorted(set(people.tolist()))
    log.info("Своя выборка: %d кадров, %d участников (%s)", len(own), len(names), ", ".join(names))
    if len(names) < args.min_people:
        raise SystemExit(
            f"Участников {len(names)}, нужно не меньше {args.min_people}: на меньшем числе людей оценка нечестная "
            "(модель запоминает лица). Соберите выборку в демонстрации или уменьшите --min-people для пробы."
        )

    device = pick_device()
    base, cfg = load_checkpoint(Path(args.checkpoint), device)
    base = base.to(device)
    splits = build_splits(cfg.data, cfg.seed, base_dir)
    # Тест для проверки «не забыла»: FER+ у моделей на метках FER+, иначе исходный FER-2013.
    fer_train, fer_test = splits.train, splits.tests.get("ferplus", splits.tests["fer2013"])
    level = cfg.augment.level

    # Перекрестная проверка по людям: исходная модель и дообученная на одних и тех же новых людях.
    base_probs = predict(base, own, device, tta_flip=False)
    folds = []
    tuned_probs = np.zeros_like(base_probs)
    splitter = GroupKFold(n_splits=min(args.folds, len(names)))
    for k, (train_idx, test_idx) in enumerate(splitter.split(own.images, own.labels, groups=people), 1):
        tuned = finetune(base, own.subset(train_idx), fer_train, args, device, level)
        tuned_probs[test_idx] = predict(tuned, own.subset(test_idx), device, tta_flip=False)
        held = sorted(set(people[test_idx].tolist()))
        fold = {
            "fold": k,
            "people": held,
            "n": int(len(test_idx)),
            "base_accuracy": round(accuracy(own.labels[test_idx], base_probs[test_idx]), 4),
            "tuned_accuracy": round(accuracy(own.labels[test_idx], tuned_probs[test_idx]), 4),
        }
        folds.append(fold)
        log.info("Фолд %d (%s): %.3f → %.3f", k, ", ".join(held), fold["base_accuracy"], fold["tuned_accuracy"])

    per_person = {
        p: {
            "n": int((people == p).sum()),
            "base": round(accuracy(own.labels[people == p], base_probs[people == p]), 4),
            "tuned": round(accuracy(own.labels[people == p], tuned_probs[people == p]), 4),
        }
        for p in names
    }
    recall = {
        label: {
            "base": round(accuracy(own.labels[own.labels == i], base_probs[own.labels == i]), 3),
            "tuned": round(accuracy(own.labels[own.labels == i], tuned_probs[own.labels == i]), 3),
        }
        for i, label in enumerate(LABELS)
        if (own.labels == i).any()
    }
    own_base, own_tuned = accuracy(own.labels, base_probs), accuracy(own.labels, tuned_probs)

    # Итоговая модель – на всей своей выборке; проверка, что FER-2013 не забыт.
    final = finetune(base, own, fer_train, args, device, level)
    fer_base = accuracy(fer_test.labels, predict(base, fer_test, device, tta_flip=False))
    fer_tuned = accuracy(fer_test.labels, predict(final, fer_test, device, tta_flip=False))
    gain, fer_drop = own_tuned - own_base, fer_base - fer_tuned
    accepted = gain >= args.min_gain and fer_drop <= args.max_fer_drop
    report: dict[str, Any] = {
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checkpoint": args.checkpoint,
        "own": {"frames": int(len(own)), "people": names, "recordings": int(len(set(recordings.tolist())))},
        "params": {k: getattr(args, k) for k in ("epochs", "lr", "batch_size", "fer_replay", "folds", "seed")},
        "new_people": {
            "base_accuracy": round(own_base, 4),
            "tuned_accuracy": round(own_tuned, 4),
            "base_by_recording": round(by_recording(own.labels, base_probs, recordings), 4),
            "tuned_by_recording": round(by_recording(own.labels, tuned_probs, recordings), 4),
            "recall": recall,
            "per_person": per_person,
            "folds": folds,
        },
        "fer2013_test": {"base_accuracy": round(fer_base, 4), "tuned_accuracy": round(fer_tuned, 4)},
        "rule": {"min_gain": args.min_gain, "max_fer_drop": args.max_fer_drop, "accepted": accepted},
    }
    log.info(
        "Новые люди: %.3f → %.3f (%+.1f п. п.); FER-2013 тест: %.3f → %.3f; принято: %s",
        own_base,
        own_tuned,
        gain * 100,
        fer_base,
        fer_tuned,
        accepted,
    )

    if args.export:
        if not accepted:
            log.warning("Правило принятия не выполнено – модель не выпускается")
        else:
            from fer_training.export import export_onnx

            run_dir = base_dir / "runs" / "ft-own" / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            run_dir.mkdir(parents=True)
            torch.save(
                {"state_dict": final.state_dict(), "config": cfg.to_dict(), "epoch": args.epochs}, run_dir / "best.pt"
            )
            (run_dir / "metrics.json").write_text(
                json.dumps({"test": {"fer2013": {"accuracy": fer_tuned}}, "own": report}, ensure_ascii=False, indent=2),
                "utf-8",
            )
            onnx = export_onnx(run_dir / "best.pt", Path(args.out), args.export, base_dir)
            card_path = onnx.parent / "model_card.json"
            card = json.loads(card_path.read_text("utf-8"))
            card["metrics"]["own_test_accuracy"] = round(own_tuned, 4)
            card["datasets"].append(f"own ({len(names)} чел., {len(own)} кадров)")
            card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
            report["exported"] = str(onnx)

    out = Path("results") / "finetune_own.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps({k: report[k] for k in ("own", "new_people", "fer2013_test", "rule")}, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
