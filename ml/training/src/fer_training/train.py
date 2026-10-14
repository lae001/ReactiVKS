"""Обучение и оценка. Каждый запуск – каталог runs/<name>/<время>/ с конфигурацией, историей, весами и метриками."""

from __future__ import annotations

import csv
import json
import logging
import math
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from emotion_service.labels import LABELS, NUM_CLASSES
from torch import nn
from torch.utils.data import DataLoader, WeightedRandomSampler

from fer_training.augment import build_train_transform
from fer_training.config import ExperimentConfig, config_from_dict
from fer_training.data import FaceDataset, ImageSet, build_splits, to_tensor
from fer_training.metrics import compute_metrics, plot_confusion, summary_line
from fer_training.models import EmotionNet, build_model, count_parameters

log = logging.getLogger(__name__)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def pick_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def class_weights(counts: np.ndarray) -> torch.Tensor:
    """Обратная частота, смягченная корнем: полная обратная частота переобучает disgust (≈ 400 примеров)."""
    weights = (counts.sum() / (NUM_CLASSES * np.clip(counts, 1, None))) ** 0.5
    return torch.tensor(weights / weights.mean(), dtype=torch.float32)


@torch.no_grad()
def predict(
    model: nn.Module,
    data: ImageSet,
    device: torch.device,
    tta_flip: bool = True,
    amp: bool = True,
    batch_size: int = 512,
) -> np.ndarray:
    """Вероятности (N, 7); при tta_flip – среднее по исходному и отраженному кропу."""
    model.eval()
    images = to_tensor(data.images)
    out: list[np.ndarray] = []
    for start in range(0, len(images), batch_size):
        batch = images[start : start + batch_size].to(device, non_blocking=True)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=amp and device.type == "cuda"):
            probs = model(batch).float().softmax(dim=1)
            if tta_flip:
                probs = (probs + model(batch.flip(-1)).float().softmax(dim=1)) / 2
        out.append(probs.cpu().numpy())
    return np.concatenate(out)


def _param_groups(model: nn.Module, weight_decay: float) -> list[dict[str, Any]]:
    decay, no_decay = [], []
    for name, param in model.named_parameters():
        (no_decay if param.ndim <= 1 or name.endswith(".bias") else decay).append(param)
    return [{"params": decay, "weight_decay": weight_decay}, {"params": no_decay, "weight_decay": 0.0}]


def _lr_lambda(total_steps: int, warmup_steps: int) -> Any:
    def fn(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1 + math.cos(math.pi * min(progress, 1.0)))

    return fn


def make_run_dir(cfg: ExperimentConfig, base_dir: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = base_dir / cfg.output_dir / cfg.name / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.yaml").write_text(yaml.safe_dump(cfg.to_dict(), allow_unicode=True, sort_keys=False), "utf-8")
    return run_dir


def train(cfg: ExperimentConfig, base_dir: Path) -> Path:
    seed_everything(cfg.seed)
    device = pick_device()
    splits = build_splits(cfg.data, cfg.seed, base_dir)
    run_dir = make_run_dir(cfg, base_dir)
    log.info("Запуск %s на %s; train=%d val=%d", run_dir, device, len(splits.train), len(splits.val))
    log.info("Классы train: %s", dict(zip(LABELS, splits.train.class_counts().tolist(), strict=True)))

    tc = cfg.train
    dataset = FaceDataset(splits.train, build_train_transform(cfg.augment.level))
    sampler = None
    if tc.balance == "sampler":
        per_class = 1.0 / np.clip(splits.train.class_counts(), 1, None)
        sampler = WeightedRandomSampler(per_class[splits.train.labels].tolist(), len(splits.train), replacement=True)
    loader = DataLoader(
        dataset,
        batch_size=tc.batch_size,
        shuffle=sampler is None,
        sampler=sampler,
        num_workers=tc.num_workers,
        pin_memory=device.type == "cuda",
        drop_last=True,
        persistent_workers=tc.num_workers > 0,
    )

    model = build_model(cfg.model).to(device, memory_format=torch.channels_last)
    log.info("Модель %s: %.2f M параметров", cfg.model.arch, count_parameters(model) / 1e6)
    weight = class_weights(splits.train.class_counts()).to(device) if tc.balance == "weighted_loss" else None
    criterion = nn.CrossEntropyLoss(weight=weight, label_smoothing=tc.label_smoothing)
    optimizer = torch.optim.AdamW(_param_groups(model, tc.weight_decay), lr=tc.lr)
    steps_per_epoch = min(len(loader), tc.max_steps_per_epoch or len(loader))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, _lr_lambda(tc.epochs * steps_per_epoch, int(tc.warmup_epochs * steps_per_epoch))
    )
    use_amp = tc.amp and device.type == "cuda"

    history: list[dict[str, Any]] = []
    best_score, best_epoch = -1.0, -1
    started = time.perf_counter()
    for epoch in range(1, tc.epochs + 1):
        model.train()
        epoch_start = time.perf_counter()
        loss_sum, correct, seen = 0.0, 0, 0
        for step, (images, labels) in enumerate(loader):
            if step >= steps_per_epoch:
                break
            images = images.to(device, non_blocking=True).contiguous(memory_format=torch.channels_last)
            labels = labels.to(device, non_blocking=True)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=use_amp):
                logits = model(images)
                loss = criterion(logits.float(), labels)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            scheduler.step()
            loss_sum += loss.item() * len(labels)
            correct += int((logits.argmax(1) == labels).sum())
            seen += len(labels)

        val = compute_metrics(splits.val.labels, predict(model, splits.val, device, tc.tta_flip, tc.amp))
        row = {
            "epoch": epoch,
            "lr": optimizer.param_groups[0]["lr"],
            "train_loss": loss_sum / seen,
            "train_acc": correct / seen,
            "val_acc": val["accuracy"],
            "val_macro_f1": val["macro_f1"],
            "seconds": time.perf_counter() - epoch_start,
        }
        history.append(row)
        score = val[tc.select_metric]
        if score > best_score:
            best_score, best_epoch = score, epoch
            torch.save(
                {"state_dict": model.state_dict(), "config": cfg.to_dict(), "epoch": epoch, "val": val},
                run_dir / "best.pt",
            )
        log.info(
            "Эпоха %d/%d: loss=%.4f train_acc=%.4f val %s (%.0f с)%s",
            epoch,
            tc.epochs,
            row["train_loss"],
            row["train_acc"],
            summary_line(val),
            row["seconds"],
            " *" if best_epoch == epoch else "",
        )

    with (run_dir / "history.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(history[0]))
        writer.writeheader()
        writer.writerows(history)

    checkpoint = torch.load(run_dir / "best.pt", map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    results: dict[str, Any] = {
        "name": cfg.name,
        "arch": cfg.model.arch,
        "params_m": round(count_parameters(model) / 1e6, 2),
        "best_epoch": best_epoch,
        "train_minutes": round((time.perf_counter() - started) / 60, 1),
        "val": checkpoint["val"],
        "test": evaluate_sets(model, splits.tests, device, run_dir, tc.tta_flip, tc.amp),
    }
    (run_dir / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    log.info("Готово: %s; лучшая эпоха %d", run_dir, best_epoch)
    return run_dir


def evaluate_sets(
    model: EmotionNet, tests: dict[str, ImageSet], device: torch.device, out_dir: Path, tta_flip: bool, amp: bool
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, data in tests.items():
        metrics = compute_metrics(data.labels, predict(model, data, device, tta_flip, amp))
        plot_confusion(metrics["confusion"], out_dir / f"confusion_{name}.png", f"{name}: {summary_line(metrics)}")
        log.info("Тест %s: %s", name, summary_line(metrics))
        results[name] = metrics
    return results


def load_checkpoint(path: Path, device: torch.device | None = None) -> tuple[EmotionNet, ExperimentConfig]:
    checkpoint = torch.load(path, map_location=device or "cpu", weights_only=False)
    cfg = config_from_dict(checkpoint["config"])
    model = build_model(cfg.model, pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval(), cfg
