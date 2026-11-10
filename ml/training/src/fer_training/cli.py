"""fer-train: подготовка данных, обучение, подбор гиперпараметров, экспорт, замер задержки, сводная таблица.

Пути в конфигурациях – относительно каталога ml/training (рабочий каталог запуска).
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
from pathlib import Path

import yaml


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )


def cmd_prepare(args: argparse.Namespace) -> None:
    from emotion_service.labels import LABELS

    from fer_training.data import load_fer2013

    for name, data in load_fer2013(Path(args.fer2013)).items():
        counts = dict(zip(LABELS, data.class_counts().tolist(), strict=True))
        print(f"{name}: {len(data)} {counts}")


def cmd_train(args: argparse.Namespace) -> None:
    from fer_training.config import load_config
    from fer_training.train import train

    print(train(load_config(args.config, args.overrides), Path.cwd()))


def cmd_sweep(args: argparse.Namespace) -> None:
    """Перебор сетки: --grid train.lr=[3e-4,1e-3] train.balance=[none,sampler]."""
    from fer_training.config import load_config
    from fer_training.train import train

    keys, values = [], []
    for item in args.grid:
        key, _, text = item.partition("=")
        keys.append(key)
        values.append(yaml.safe_load(text))
    base = load_config(args.config, args.overrides)
    for combo in itertools.product(*values):
        overrides = [*args.overrides, *(f"{k}={json.dumps(v)}" for k, v in zip(keys, combo, strict=True))]
        suffix = "-".join(f"{k.split('.')[-1]}{v}" for k, v in zip(keys, combo, strict=True))
        overrides.append(f"name={base.name}-{suffix}")
        print(train(load_config(args.config, overrides), Path.cwd()))


def cmd_export(args: argparse.Namespace) -> None:
    from fer_training.export import export_onnx

    checkpoint = Path(args.checkpoint)
    out_dir = Path(args.out) if args.out else checkpoint.parent
    print(export_onnx(checkpoint, out_dir, args.version, Path.cwd(), opset=args.opset))


def cmd_bench(args: argparse.Namespace) -> None:
    from fer_training.export import bench_cpu

    print(json.dumps(bench_cpu(Path(args.onnx), threads=args.threads), ensure_ascii=False, indent=2))


def cmd_quantize(args: argparse.Namespace) -> None:
    from fer_training.export import quantize_int8

    print(quantize_int8(Path(args.onnx), Path.cwd(), calibration_size=args.calibration, method=args.method))


def cmd_bench_gpu(args: argparse.Namespace) -> None:
    from fer_training.export import bench_gpu

    print(json.dumps(bench_gpu(Path(args.checkpoint)), ensure_ascii=False, indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    """Строки таблицы для experiments.md по каталогам запусков."""
    columns = ["Запуск", "Архитектура", "Параметры, M", "Эпоха", "Val acc", "Test acc", "Test macro-F1", "Private acc"]
    print("| " + " | ".join([*columns, "CPU, мс/лицо"]) + " |")
    print("|---|---|---|---|---|---|---|---|---|")
    for run in map(Path, args.runs):
        metrics = json.loads((run / "metrics.json").read_text("utf-8"))
        latency_path = run / "latency.json"
        latency = json.loads(latency_path.read_text("utf-8"))["ms_per_face"]["1"] if latency_path.exists() else "–"
        test = metrics["test"]
        print(
            f"| {run.parent.name}/{run.name} | {metrics['arch']} | {metrics['params_m']} | {metrics['best_epoch']} "
            f"| {metrics['val']['accuracy']:.4f} | {test['fer2013']['accuracy']:.4f} "
            f"| {test['fer2013']['macro_f1']:.4f} | {test['fer2013_private']['accuracy']:.4f} | {latency} |"
        )


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="fer-train")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="загрузить FER-2013 из parquet и собрать кеш")
    p.add_argument("--fer2013", default="data/fer2013")
    p.set_defaults(func=cmd_prepare)

    for name, func in (("train", cmd_train), ("sweep", cmd_sweep)):
        p = sub.add_parser(name)
        p.add_argument("--config", required=True)
        p.add_argument("overrides", nargs="*", help="ключ=значение, например train.lr=3e-4")
        if name == "sweep":
            p.add_argument("--grid", nargs="+", required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("export")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--out")
    p.add_argument("--opset", type=int, default=17)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("bench")
    p.add_argument("--onnx", required=True)
    p.add_argument("--threads", type=int, default=4)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("quantize", help="статическая INT8-квантизация ONNX с калибровкой на валидации")
    p.add_argument("--onnx", required=True)
    p.add_argument("--calibration", type=int, default=512)
    p.add_argument("--method", choices=["minmax", "percentile", "entropy"], default="percentile")
    p.set_defaults(func=cmd_quantize)

    p = sub.add_parser("bench-gpu", help="задержка PyTorch на GPU")
    p.add_argument("--checkpoint", required=True)
    p.set_defaults(func=cmd_bench_gpu)

    p = sub.add_parser("report")
    p.add_argument("runs", nargs="+")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
