"""Модели: обертка EmotionNet приводит канонический кроп к входу сети внутри графа.

Вход – (N, 1, 48, 48) float32 в [0, 1], выход – логиты (N, 7). Увеличение, повтор канала и нормализация ImageNet
экспортируются в ONNX вместе с сетью, поэтому сервис подает модели ровно то, что вернул общий препроцессинг.
"""

from __future__ import annotations

import timm
import torch
import torch.nn.functional as F
from emotion_service.labels import NUM_CLASSES
from torch import nn

from fer_training.config import ModelConfig

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Короткие имена архитектур → модели timm с весами ImageNet-1k.
TIMM_ARCHS = {
    "resnet18": "resnet18.a1_in1k",
    "efficientnet_b0": "efficientnet_b0.ra_in1k",
    "mobilenetv3_large": "mobilenetv3_large_100.ra_in1k",
    "convnext_tiny": "convnext_tiny.fb_in1k",
}


class SimpleCNN(nn.Module):
    """Базовая модель без предобучения (EMO-28): 4 блока свертка-свертка-пулинг на родном разрешении 48×48."""

    def __init__(self, num_classes: int = NUM_CLASSES, drop_rate: float = 0.3) -> None:
        super().__init__()

        def block(cin: int, cout: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
            )

        self.features = nn.Sequential(block(3, 64), block(64, 128), block(128, 256), block(256, 512))
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(drop_rate), nn.Linear(512, num_classes)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


class EmotionNet(nn.Module):
    def __init__(self, backbone: nn.Module, input_size: int, mean: tuple[float, ...], std: tuple[float, ...]) -> None:
        super().__init__()
        self.backbone = backbone
        self.input_size = input_size
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[-1] != self.input_size:
            x = F.interpolate(x, size=(self.input_size, self.input_size), mode="bilinear", align_corners=False)
        x = x.repeat(1, 3, 1, 1)
        x = (x - self.mean) / self.std
        return self.backbone(x)


def build_model(cfg: ModelConfig, pretrained: bool | None = None) -> EmotionNet:
    use_pretrained = cfg.pretrained if pretrained is None else pretrained
    if cfg.arch == "simple_cnn":
        return EmotionNet(SimpleCNN(drop_rate=cfg.drop_rate), cfg.input_size, (0.5,) * 3, (0.25,) * 3)
    name = TIMM_ARCHS.get(cfg.arch, cfg.arch)
    backbone = timm.create_model(name, pretrained=use_pretrained, num_classes=NUM_CLASSES, drop_rate=cfg.drop_rate)
    return EmotionNet(backbone, cfg.input_size, IMAGENET_MEAN, IMAGENET_STD)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
