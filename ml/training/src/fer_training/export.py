"""Экспорт в ONNX, проверка эквивалентности PyTorch ↔ ONNX Runtime, карточка модели и замер задержки на CPU."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import torch
from emotion_service.labels import LABELS
from emotion_service.preprocessing import CROP_SIZE, PREPROCESSING_ID
from torch import nn

from fer_training.data import build_splits, to_tensor
from fer_training.train import load_checkpoint

log = logging.getLogger(__name__)

LICENSE_NOTE = "Только некоммерческое учебное использование (лицензии FER-2013 / RAF-DB / AffectNet)"


class WithSoftmax(nn.Module):
    """Сервису нужны вероятности: softmax встраивается в граф."""

    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x).softmax(dim=1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_onnx(
    checkpoint: Path, out_dir: Path, version: str, base_dir: Path, opset: int = 17, check_n: int = 500
) -> Path:
    model, cfg = load_checkpoint(checkpoint)
    wrapped = WithSoftmax(model).eval()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"emotion-{cfg.model.arch.replace('_', '')}"
    onnx_path = out_dir / f"{name}-v{version}.onnx"
    dummy = torch.rand(2, 1, CROP_SIZE, CROP_SIZE)
    torch.onnx.export(
        wrapped,
        (dummy,),
        str(onnx_path),
        input_names=["face"],
        output_names=["probs"],
        dynamic_axes={"face": {0: "n"}, "probs": {0: "n"}},
        opset_version=opset,
        dynamo=False,
    )

    # Эквивалентность на реальных изображениях теста FER-2013.
    tests = build_splits(cfg.data, cfg.seed, base_dir).tests["fer2013"]
    images = to_tensor(tests.images[:check_n])
    with torch.no_grad():
        expected = wrapped(images).numpy()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"face": images.numpy()})[0]
    max_diff = float(np.abs(expected - actual).max())
    agreement = float((expected.argmax(1) == actual.argmax(1)).mean())
    log.info("PyTorch ↔ ONNX Runtime: макс. отклонение %.2e, совпадение классов %.4f", max_diff, agreement)
    if max_diff >= 1e-3:
        raise RuntimeError(f"ONNX расходится с PyTorch: {max_diff:.2e} ≥ 1e-3")

    metrics_path = checkpoint.parent / "metrics.json"
    metrics: dict[str, Any] = json.loads(metrics_path.read_text("utf-8")) if metrics_path.exists() else {}
    test = metrics.get("test", {})
    card = {
        "name": name,
        "version": version,
        "model_version": f"{name}@{version}",
        "arch": cfg.model.arch,
        "labels": list(LABELS),
        "input": {
            "name": "face",
            "shape": [1, CROP_SIZE, CROP_SIZE],
            "color": "gray",
            "dtype": "float32",
            "range": [0.0, 1.0],
            "note": "увеличение до входа сети и нормализация – внутри графа",
        },
        "output": {"name": "probs", "kind": "softmax"},
        "preprocessing": PREPROCESSING_ID,
        "metrics": {
            "fer2013_test_accuracy": test.get("fer2013", {}).get("accuracy"),
            "fer2013_test_macro_f1": test.get("fer2013", {}).get("macro_f1"),
            "fer2013_private_accuracy": test.get("fer2013_private", {}).get("accuracy"),
            "own_test_accuracy": None,
        },
        "onnx": {
            "file": onnx_path.name,
            "sha256": sha256(onnx_path),
            "opset": opset,
            "max_abs_diff_vs_torch": max_diff,
        },
        "datasets": ["FER-2013"] + (["RAF-DB"] if cfg.data.rafdb else []) + [Path(f).name for f in cfg.data.folders],
        "license_note": LICENSE_NOTE,
    }
    (out_dir / "model_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
    log.info("Экспортировано: %s", onnx_path)
    return onnx_path


def bench_cpu(
    onnx_path: Path, threads: int = 4, batches: tuple[int, ...] = (1, 10), iterations: int = 100
) -> dict[str, Any]:
    """Задержка ONNX Runtime на CPU, мс на лицо; критерий выбора модели – ≤ 15 мс/лицо (docs/ml/ml-model.md)."""
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    result: dict[str, Any] = {"threads": threads, "cpu": _cpu_name(), "ms_per_face": {}, "ms_per_batch": {}}
    for batch in batches:
        x = rng.random((batch, 1, CROP_SIZE, CROP_SIZE), dtype=np.float32)
        for _ in range(10):
            session.run(None, {"face": x})
        timings = []
        for _ in range(iterations):
            start = time.perf_counter()
            session.run(None, {"face": x})
            timings.append((time.perf_counter() - start) * 1000)
        median = float(np.median(timings))
        result["ms_per_batch"][str(batch)] = round(median, 2)
        result["ms_per_face"][str(batch)] = round(median / batch, 2)
    (onnx_path.parent / "latency.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    return result


def _cpu_name() -> str:
    import platform

    return platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown")
