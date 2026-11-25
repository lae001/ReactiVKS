"""Аугментации, приближающие обучающие кропы к условиям видеовстречи (docs/ml/ml-model.md).

Работают на каноническом кропе 48×48 (серое): дешево на CPU и не создают деталей, которых нет в кадре ВКС.
"""

from __future__ import annotations

import albumentations as A

from fer_training.config import AugmentLevel


def build_train_transform(level: AugmentLevel) -> A.Compose | None:
    if level == "none":
        return None
    geometry = [
        A.HorizontalFlip(p=0.5),
        # Поворот головы и неточная рамка детектора.
        A.Affine(scale=(0.9, 1.1), translate_percent=(-0.06, 0.06), rotate=(-15, 15), border_mode=1, p=0.7),
    ]
    if level == "basic":
        return A.Compose([*geometry, A.RandomBrightnessContrast(0.2, 0.2, p=0.5)])
    return A.Compose(
        [
            *geometry,
            # Слабое и неравномерное освещение, автоэкспозиция веб-камеры.
            A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
            A.RandomGamma(gamma_limit=(70, 150), p=0.3),
            # Расфокус и смаз при движении.
            A.OneOf([A.GaussianBlur(blur_limit=(3, 3)), A.MotionBlur(blur_limit=(3, 5))], p=0.2),
            # Низкое разрешение simulcast-слоя и артефакты VP8/H.264.
            A.Downscale(scale_range=(0.5, 0.9), p=0.25),
            A.ImageCompression(quality_range=(30, 90), p=0.4),
            A.GaussNoise(std_range=(0.01, 0.05), p=0.2),
            # Частичные окклюзии: рука, микрофон, очки.
            A.CoarseDropout(num_holes_range=(1, 2), hole_height_range=(0.1, 0.3), hole_width_range=(0.1, 0.3), p=0.3),
        ]
    )
