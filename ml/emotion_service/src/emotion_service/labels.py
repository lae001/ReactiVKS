"""Классы эмоций. Порядок фиксирован: он совпадает с разметкой FER-2013 и записывается в model_card.json."""

from typing import Final

LABELS: Final[tuple[str, ...]] = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")
NUM_CLASSES: Final[int] = len(LABELS)
