"""Второй источник признаков эмоций: логистическая регрессия по 52 мимическим коэффициентам MediaPipe.

CNN смотрит на пиксели кропа 48×48, коэффициенты – на геометрию 478 точек (подняты ли брови, открыт ли рот,
расширены ли глаза). Ошибки у них разные, поэтому их среднее геометрическое точнее каждого по отдельности.
Голова обучается в ml/training (scripts/train_blendshape_head.py) на тех же сплитах FER-2013; вес смешивания
подбирается на валидации и хранится вместе с весами в blendshape_head.json рядом с карточкой модели.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from emotion_service.labels import LABELS

# Зоны лица, которые закрывают очки и борода: их мимические коэффициенты при этом недостоверны (оправа и блики
# сбивают точки век и бровей, борода – губ и подбородка) и заменяются средним по обучению, т. е. «нет сведений».
OCCLUDED_ZONES: dict[str, tuple[str, ...]] = {
    "glasses": ("brow", "eyeBlink", "eyeLook", "eyeSquint", "eyeWide"),
    "beard": ("jaw", "mouth", "cheek", "noseSneer"),
}


def condition_of(occluded: tuple[str, ...]) -> str:
    """Условие для выбора веса смешивания: none | glasses | beard | glasses_beard."""
    return "_".join(name for name in ("glasses", "beard") if name in occluded) or "none"


def fuse(cnn: np.ndarray, head: np.ndarray, weight: float) -> np.ndarray:
    """Взвешенное среднее геометрическое распределений: p ∝ cnn^(1−w) · head^w."""
    log = (1 - weight) * np.log(np.clip(cnn, 1e-6, 1)) + weight * np.log(np.clip(head, 1e-6, 1))
    log -= log.max(axis=-1, keepdims=True)
    probs = np.exp(log)
    result: np.ndarray = probs / probs.sum(axis=-1, keepdims=True)
    return result


@dataclass(frozen=True)
class BlendshapeHead:
    names: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray  # (7, n)
    intercept: np.ndarray  # (7,)
    weight: float  # вес головы при смешивании с CNN (лицо без очков и бороды)
    # Вес по условию (none | glasses | beard | glasses_beard), подобран на валидации с синтетическими очками и
    # бородой (train_blendshape_head.py); нет условия – weight.
    weights: dict[str, float] | None = None

    @classmethod
    def load(cls, path: str | Path) -> BlendshapeHead:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if tuple(raw["labels"]) != LABELS:
            raise ValueError(f"Порядок классов головы {raw['labels']} не совпадает с контрактом {LABELS}")
        return cls(
            names=tuple(raw["features"]),
            mean=np.asarray(raw["mean"], np.float32),
            std=np.asarray(raw["std"], np.float32),
            coef=np.asarray(raw["coef"], np.float32),
            intercept=np.asarray(raw["intercept"], np.float32),
            weight=float(raw["fusion_weight"]),
            weights={k: float(v) for k, v in raw.get("fusion_weights", {}).items()} or None,
        )

    def predict(self, features: np.ndarray) -> np.ndarray:
        """features – (n,) или (N, n) в порядке names → вероятности (…, 7)."""
        logits = ((features - self.mean) / self.std) @ self.coef.T + self.intercept
        logits = logits - logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits)
        probs: np.ndarray = exp / exp.sum(axis=-1, keepdims=True)
        return probs

    def fuse(self, cnn_probs: np.ndarray, features: np.ndarray) -> np.ndarray:
        return fuse(cnn_probs, self.predict(features), self.weight)

    def mask(self, features: np.ndarray, occluded: tuple[str, ...]) -> np.ndarray:
        """Коэффициенты закрытых зон → среднее по обучению (после стандартизации – 0, т. е. не влияют)."""
        out = np.array(features, dtype=np.float32, copy=True)
        for name in occluded:
            prefixes = OCCLUDED_ZONES.get(name, ())
            for i, feature in enumerate(self.names):
                if feature.startswith(prefixes):
                    out[..., i] = self.mean[i]
        return out

    def fuse_with_attributes(
        self, cnn_probs: np.ndarray, features: np.ndarray, occluded: tuple[str, ...]
    ) -> np.ndarray:
        """Смешивание с учетом очков и бороды: закрытые зоны отключены, вес – свой для условия."""
        weight = (self.weights or {}).get(condition_of(occluded), self.weight)
        return fuse(cnn_probs, self.predict(self.mask(features, occluded)), weight)
