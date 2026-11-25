"""Детектор внешних признаков лица: очки и борода (включая усы и эспаньолку) – CelebA-attrs-20k.

Зачем: очки закрывают глаза и брови, борода – рот и подбородок; именно по этим зонам модель и мимика сетки лица
судят об эмоции. Сервис определяет признаки и учитывает их при смешивании CNN с мимикой
(emotion_service/attributes.py, experiments.md, §9).

Лица CelebA вырезаются тем же YuNet и тем же кропом, что и в сервисе (attributes.attribute_crop): 96×96 RGB,
сторона max(w, h) × 1,5 – с запасом вниз под бороду. Модель – MobileNetV3-Large (ImageNet), два выхода-логита,
BCE с pos_weight; пороги выбираются на валидации по F1, тест – только для итоговых чисел.

Запуск из ml/training:  uv run python scripts/train_attributes.py --out ../models/attributes
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import pandas as pd
import timm
import torch
from emotion_service.attributes import ATTRIBUTES, CROP_SIDE, attribute_crop
from emotion_service.detection import YuNetDetector
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from torch import nn

MODELS = Path(__file__).absolute().parents[2] / "models"
DATA = Path("data/celeba")


def labels_of(frame: pd.DataFrame) -> np.ndarray:
    glasses = frame["Eyeglasses"].to_numpy() == 1
    beard = (
        (frame["No_Beard"].to_numpy() == -1) | (frame["Goatee"].to_numpy() == 1) | (frame["Mustache"].to_numpy() == 1)
    )
    return np.stack([glasses, beard], axis=1).astype(np.float32)


def prepare(split: str, detector: YuNetDetector) -> tuple[np.ndarray, np.ndarray]:
    """Кропы через YuNet (кеш data/celeba/<split>_crops.npz); изображения без найденного лица пропускаются."""
    cache = DATA / f"{split}_crops.npz"
    if cache.exists():
        with np.load(cache) as packed:
            return packed["x"], packed["y"]
    frame = pd.read_parquet(
        DATA / f"{split}.parquet", columns=["image", "Eyeglasses", "No_Beard", "Goatee", "Mustache"]
    )
    labels = labels_of(frame)
    crops, keep = [], []
    for i, cell in enumerate(frame["image"]):
        bgr = cv2.imdecode(np.frombuffer(cell["bytes"], np.uint8), cv2.IMREAD_COLOR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        faces = detector.detect(rgb)
        if faces:
            crops.append(attribute_crop(rgb, faces[0]))
            keep.append(i)
    x, y = np.stack(crops), labels[keep]
    print(f"{split}: лицо найдено {len(keep) / len(frame):.3f} ({len(keep)} из {len(frame)})")
    np.savez_compressed(cache, x=x, y=y)
    return x, y


class AttributeNet(nn.Module):
    """Вход – (N, 96, 96, 3) uint8 RGB как float32 0..255; нормализация ImageNet внутри графа; выход – вероятности."""

    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        self.backbone = timm.create_model(
            "mobilenetv3_large_100.ra_in1k", pretrained=pretrained, num_classes=len(ATTRIBUTES)
        )
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1) * 255)
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1) * 255)

    def logits(self, x: torch.Tensor) -> torch.Tensor:
        x = x.permute(0, 3, 1, 2)
        return self.backbone((x - self.mean) / self.std)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.logits(x))


def augment(batch: torch.Tensor) -> torch.Tensor:
    """Отражение, яркость/контраст, слабое размытие сжатием – условия веб-камеры."""
    flip = torch.rand(len(batch), device=batch.device) < 0.5
    batch = torch.where(flip.view(-1, 1, 1, 1), batch.flip(2), batch)
    gain = 0.7 + 0.6 * torch.rand(len(batch), 1, 1, 1, device=batch.device)
    bias = 40 * (torch.rand(len(batch), 1, 1, 1, device=batch.device) - 0.5)
    return (batch * gain + bias).clamp(0, 255)


@torch.no_grad()
def predict(model: AttributeNet, x: np.ndarray, device: torch.device) -> np.ndarray:
    model.eval()
    out = [model(torch.from_numpy(x[i : i + 256]).float().to(device)).cpu().numpy() for i in range(0, len(x), 256)]
    return np.concatenate(out)


def evaluate(y: np.ndarray, p: np.ndarray, thresholds: list[float]) -> dict[str, dict[str, float]]:
    report = {}
    for j, name in enumerate(ATTRIBUTES):
        pred = p[:, j] >= thresholds[j]
        report[name] = {
            "auc": round(float(roc_auc_score(y[:, j], p[:, j])), 4),
            "f1": round(float(f1_score(y[:, j], pred)), 4),
            "precision": round(float(precision_score(y[:, j], pred)), 4),
            "recall": round(float(recall_score(y[:, j], pred)), 4),
            "accuracy": round(float((pred == y[:, j]).mean()), 4),
            "positives": int(y[:, j].sum()),
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../models/attributes")
    parser.add_argument("--epochs", type=int, default=8)
    args = parser.parse_args()
    torch.manual_seed(42)

    detector = YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx")
    xt, yt = prepare("train", detector)
    xv, yv = prepare("validation", detector)
    xs, ys = prepare("test", detector)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AttributeNet().to(device)
    pos_weight = torch.tensor((len(yt) - yt.sum(0)) / yt.sum(0), dtype=torch.float32, device=device).sqrt()
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.05)
    steps = args.epochs * (len(xt) // 128)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=1e-3, total_steps=steps, pct_start=0.1)
    x_train, y_train = torch.from_numpy(xt), torch.from_numpy(yt)
    best_auc, best_state = -1.0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        started = time.perf_counter()
        order = torch.randperm(len(x_train))
        for i in range(0, len(order) - 127, 128):
            index = order[i : i + 128]
            batch = augment(x_train[index].float().to(device))
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                loss = criterion(model.logits(batch).float(), y_train[index].to(device))
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
        pv = predict(model, xv, device)
        auc = float(np.mean([roc_auc_score(yv[:, j], pv[:, j]) for j in range(len(ATTRIBUTES))]))
        print(f"эпоха {epoch}: val AUC {auc:.4f} ({time.perf_counter() - started:.0f} с)")
        if auc > best_auc:
            best_auc, best_state = auc, {k: v.detach().clone() for k, v in model.state_dict().items()}
    if best_state is None:
        raise RuntimeError("Модель не обучена")
    model.load_state_dict(best_state)

    pv, ps = predict(model, xv, device), predict(model, xs, device)
    grid = np.linspace(0.05, 0.95, 91)
    thresholds = [float(max(grid, key=lambda t: f1_score(yv[:, j], pv[:, j] >= t))) for j in range(len(ATTRIBUTES))]
    report = {"val": evaluate(yv, pv, thresholds), "test": evaluate(ys, ps, thresholds)}
    print(json.dumps(report, ensure_ascii=False, indent=2))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    onnx_path = out / "attributes-mobilenetv3-v1.0.0.onnx"
    model = model.cpu().eval()
    dummy = torch.from_numpy(xs[:2]).float()
    torch.onnx.export(
        model, (dummy,), str(onnx_path), input_names=["face"], output_names=["probs"],
        dynamic_axes={"face": {0: "n"}, "probs": {0: "n"}}, opset_version=17, dynamo=False,
    )  # fmt: skip
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    diff = float(
        np.abs(
            session.run(None, {"face": xs[:256].astype(np.float32)})[0] - predict(model, xs[:256], torch.device("cpu"))
        ).max()
    )
    card = {
        "model_version": "attributes-mobilenetv3@1.0.0",
        "attributes": list(ATTRIBUTES),
        "thresholds": dict(zip(ATTRIBUTES, thresholds, strict=True)),
        "input": {"name": "face", "shape": [CROP_SIDE, CROP_SIDE, 3], "color": "RGB", "dtype": "float32",
                  "range": [0, 255]},
        "onnx": {"file": onnx_path.name, "opset": 17, "max_abs_diff_vs_torch": diff},
        "dataset": "CelebA-attrs-20k (tpremoli, ревизия eed0e62), только некоммерческое использование",
        "metrics": report,
    }  # fmt: skip
    (out / "attributes_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
    print(f"Сохранено: {onnx_path}, отклонение ONNX {diff:.2e}")


if __name__ == "__main__":
    main()
