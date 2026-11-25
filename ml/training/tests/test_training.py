"""Модульные тесты обучения без датасетов и без скачивания весов."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from fer_training.augment import build_train_transform
from fer_training.config import ExperimentConfig, ModelConfig, config_from_dict, load_config
from fer_training.data import ImageSet, deduplicate, is_blank, stratified_split
from fer_training.metrics import compute_metrics
from fer_training.models import build_model
from fer_training.train import class_weights


def test_overrides_and_float_coercion(tmp_path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("name: x\ntrain:\n  lr: 1e-3\n", encoding="utf-8")
    cfg = load_config(path, ["train.balance=sampler", "model.arch=simple_cnn", "train.epochs=3"])
    assert cfg.train.lr == pytest.approx(1e-3) and isinstance(cfg.train.lr, float)
    assert cfg.train.balance == "sampler" and cfg.model.arch == "simple_cnn" and cfg.train.epochs == 3
    assert config_from_dict(cfg.to_dict()) == cfg
    with pytest.raises(KeyError):
        load_config(None, ["train.unknown=1"])


def _images(values: list[int]) -> np.ndarray:
    return np.stack([np.full((48, 48), v, np.uint8) for v in values])


def test_deduplicate_removes_leaks_conflicts_and_copies() -> None:
    train = ImageSet(_images([1, 1, 2, 2, 3, 4, 5, 5]), np.array([0, 0, 1, 2, 3, 4, 5, 5]), "t")
    test = ImageSet(_images([4]), np.array([4]), "test")
    clean, stats = deduplicate(train, [test])
    assert stats == {"leaked_into_test": 1, "label_conflicts": 2, "duplicates": 2}
    assert sorted(clean.images[:, 0, 0].tolist()) == [1, 3, 5]


def test_blank_detection() -> None:
    noisy = np.random.default_rng(0).integers(0, 255, (1, 48, 48), dtype=np.uint8)
    assert is_blank(np.concatenate([_images([7]), noisy])).tolist() == [True, False]


def test_stratified_split_keeps_class_shares() -> None:
    labels = np.repeat(np.arange(7), [400, 40, 400, 700, 480, 310, 490])
    data = ImageSet(np.zeros((len(labels), 48, 48), np.uint8), labels, "t")
    train, val = stratified_split(data, 0.1, 42)
    assert len(train) + len(val) == len(data)
    assert np.abs(val.class_counts() / len(val) - data.class_counts() / len(data)).max() < 0.01


@pytest.mark.parametrize("level", ["none", "basic", "vks"])
def test_augmentations_keep_canonical_shape(level: str) -> None:
    transform = build_train_transform(level)  # type: ignore[arg-type]
    image = np.random.default_rng(0).integers(0, 255, (48, 48), dtype=np.uint8)
    out = image if transform is None else transform(image=image)["image"]
    assert out.shape == (48, 48) and out.dtype == np.uint8


def test_model_accepts_canonical_input_and_upsamples() -> None:
    model = build_model(ModelConfig(arch="simple_cnn", pretrained=False, input_size=64)).eval()
    with torch.no_grad():
        logits = model(torch.rand(3, 1, 48, 48))
    assert logits.shape == (3, 7)


def test_class_weights_soften_imbalance() -> None:
    weights = class_weights(np.array([4000, 400, 4000, 7000, 4800, 3100, 5000]))
    assert weights.mean().item() == pytest.approx(1.0)
    assert weights[1] == weights.max() and weights[1] / weights[3] < 7000 / 400


def test_metrics() -> None:
    labels = np.array([0, 1, 2, 3])
    probs = np.eye(7)[[0, 1, 2, 4]]
    metrics = compute_metrics(labels, probs)
    assert metrics["accuracy"] == 0.75 and metrics["n"] == 4
    assert metrics["confusion"][3][4] == 1
    assert ExperimentConfig().train.select_metric == "accuracy"


def test_ferplus_labels_majority_contempt_and_exclusions(tmp_path) -> None:
    import numpy as np

    from fer_training.data import ImageSet, ferplus_labels, relabel

    header = "Usage,Image name,neutral,happiness,surprise,sadness,anger,disgust,fear,contempt,unknown,NF\n"
    rows = [
        "Training,a.png,1,8,0,0,1,0,0,0,0,0",  # радость
        "Training,b.png,0,0,0,0,2,1,0,3,0,0",  # презрение + отвращение (4) > гнев (2) → отвращение
        "Training,c.png,5,5,0,0,0,0,0,0,0,0",  # ничья – исключается
        "PublicTest,d.png,0,0,0,0,0,0,0,0,0,10",  # не лицо – исключается
        "PrivateTest,e.png,2,0,6,0,0,0,0,0,2,0",  # удивление
    ]
    path = tmp_path / "fer2013new.csv"
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    labels = ferplus_labels(path)
    assert labels["train"].tolist() == [3, 1, -1]
    assert labels["public_test"].tolist() == [-1] and labels["private_test"].tolist() == [5]
    data = ImageSet(np.zeros((3, 48, 48), np.uint8), np.array([0, 0, 0]), "fer2013/train")
    relabeled = relabel(data, labels["train"], "ferplus/train")
    assert len(relabeled) == 2 and relabeled.labels.tolist() == [3, 1]
