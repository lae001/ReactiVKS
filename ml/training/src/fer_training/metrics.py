"""Метрики качества (EMO-26): accuracy – целевой показатель ТЗ (≥ 65 % на тесте FER-2013), macro-F1 – устойчивость
к дисбалансу классов (disgust ≈ 1,5 % выборки), матрица ошибок – какие эмоции модель путает между собой."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from emotion_service.labels import LABELS, NUM_CLASSES
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support


def compute_metrics(labels: np.ndarray, probs: np.ndarray) -> dict[str, Any]:
    preds = probs.argmax(axis=1)
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, preds, labels=range(NUM_CLASSES), zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(labels, preds)),
        "macro_f1": float(f1_score(labels, preds, average="macro", labels=range(NUM_CLASSES), zero_division=0)),
        "n": int(len(labels)),
        "per_class": {
            name: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
            for name, p, r, f, s in zip(LABELS, precision, recall, f1, support, strict=True)
        },
        "confusion": confusion_matrix(labels, preds, labels=range(NUM_CLASSES)).tolist(),
    }


def plot_confusion(confusion: list[list[int]], path: Path, title: str) -> None:
    matrix = np.asarray(confusion, dtype=np.float64)
    normalized = matrix / np.clip(matrix.sum(axis=1, keepdims=True), 1, None)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    im = ax.imshow(normalized, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(NUM_CLASSES), LABELS, rotation=45, ha="right")
    ax.set_yticks(range(NUM_CLASSES), LABELS)
    ax.set_xlabel("Предсказание")
    ax.set_ylabel("Истина")
    ax.set_title(title)
    for i in range(NUM_CLASSES):
        for j in range(NUM_CLASSES):
            value = normalized[i, j]
            ax.text(
                j, i, f"{value:.2f}", ha="center", va="center", fontsize=8, color="white" if value > 0.5 else "black"
            )
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def summary_line(metrics: dict[str, Any]) -> str:
    return f"acc={metrics['accuracy']:.4f} macro-F1={metrics['macro_f1']:.4f} (n={metrics['n']})"
