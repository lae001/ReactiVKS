"""Конфигурация эксперимента: YAML из configs/ плюс переопределения из командной строки (`train.lr=3e-4`)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Balance = Literal["none", "weighted_loss", "sampler"]
AugmentLevel = Literal["none", "basic", "vks"]


@dataclass
class DataConfig:
    fer2013: str = "data/fer2013"
    # Каталог RAF-DB (basic) в исходной раскладке: EmoLabel/list_patition_label.txt, Image/aligned/.
    rafdb: str | None = None
    # Дополнительные датасеты в раскладке <root>/<split>/<класс>/*.jpg (например, AffectNet после конвертации).
    folders: list[str] = field(default_factory=list)
    val_fraction: float = 0.1
    # Однотонные изображения FER-2013 (без лица) исключаются из обучения; из теста – никогда.
    drop_blank: bool = True
    # Удаление из обучения копий тестовых изображений и копий с противоречивыми метками (data.deduplicate).
    dedup: bool = True


@dataclass
class ModelConfig:
    arch: str = "resnet18"
    pretrained: bool = True
    # Сторона входа сети: кроп 48×48 увеличивается внутри модели.
    input_size: int = 224
    drop_rate: float = 0.2


@dataclass
class TrainConfig:
    epochs: int = 30
    batch_size: int = 128
    lr: float = 1e-3
    weight_decay: float = 0.05
    warmup_epochs: float = 1.0
    label_smoothing: float = 0.1
    balance: Balance = "none"
    amp: bool = True
    num_workers: int = 4
    # Метрика выбора лучшей эпохи на валидации: accuracy – целевой показатель ТЗ.
    select_metric: Literal["accuracy", "macro_f1"] = "accuracy"
    # Усреднение предсказаний по исходному и отраженному кропу при оценке.
    tta_flip: bool = True
    # Ограничение числа шагов эпохи – для быстрых проверок и подбора гиперпараметров.
    max_steps_per_epoch: int | None = None


@dataclass
class AugmentConfig:
    level: AugmentLevel = "vks"
    # Вероятность синтетических очков и (независимо) бороды на обучающем изображении (fer_training.occlusions).
    occlusion: float = 0.0


@dataclass
class ExperimentConfig:
    name: str = "experiment"
    seed: int = 42
    output_dir: str = "runs"
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    augment: AugmentConfig = field(default_factory=AugmentConfig)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _build(cls: type, values: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    names = {f.name: f for f in dataclasses.fields(cls)}
    for key, value in values.items():
        if key not in names:
            raise KeyError(f"Неизвестный параметр {cls.__name__}.{key}")
        default = getattr(cls(), key)
        if dataclasses.is_dataclass(default):
            value = _build(type(default), value)
        elif isinstance(default, float) and isinstance(value, int | str):
            # YAML 1.1 читает «1e-3» как строку.
            value = float(value)
        kwargs[key] = value
    return cls(**kwargs)


def _merge(base: dict[str, Any], dotted: str, value: Any) -> None:
    node = base
    *path, leaf = dotted.split(".")
    for part in path:
        node = node.setdefault(part, {})
    node[leaf] = value


def load_config(path: str | Path | None, overrides: list[str] | None = None) -> ExperimentConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for item in overrides or []:
        key, _, text = item.partition("=")
        if not _:
            raise ValueError(f"Переопределение должно иметь вид ключ=значение: {item}")
        _merge(raw, key.strip(), yaml.safe_load(text))
    return _build(ExperimentConfig, raw)


def config_from_dict(raw: dict[str, Any]) -> ExperimentConfig:
    result: ExperimentConfig = _build(ExperimentConfig, raw)
    return result
