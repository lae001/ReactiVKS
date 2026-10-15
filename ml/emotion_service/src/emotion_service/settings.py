"""Настройки сервиса из переменных окружения (префикс ML_; LIVEKIT_* читает сам livekit-agents)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _optional_path(value: str) -> Path | None:
    path = Path(value) if value else None
    return path if path is not None and path.exists() else None


@dataclass(frozen=True)
class Settings:
    model_card: Path
    detector_model: Path
    # Сетка лица MediaPipe; пустая строка или отсутствующий файл – работа только на 5 точках YuNet.
    face_mesh_model: Path | None
    target_fps: float
    min_fps: float
    max_fps: float
    ema_alpha: float
    onnx_threads: int
    max_side: int
    worker_id: str
    # Доля загрузки CPU, при которой воркер перестает брать новые встречи (по умолчанию LiveKit Agents – 0,7).
    load_threshold: float
    # > 0 – первые N секунд анализа участника считаются его нейтральным лицом (calibration.py); 0 – выключено.
    auto_neutral_s: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            model_card=Path(_env("ML_MODEL_CARD", "../models/emotion/model_card.json")),
            detector_model=Path(_env("ML_DETECTOR_MODEL", "../models/yunet/face_detection_yunet_2023mar.onnx")),
            face_mesh_model=_optional_path(_env("ML_FACE_MESH_MODEL", "../models/mediapipe/face_landmarker.task")),
            target_fps=float(_env("ML_TARGET_FPS", "3")),
            min_fps=float(_env("ML_MIN_FPS", "2")),
            max_fps=float(_env("ML_MAX_FPS", "5")),
            ema_alpha=float(_env("ML_EMA_ALPHA", "0.4")),
            onnx_threads=int(_env("ML_ONNX_THREADS", "2")),
            max_side=int(_env("ML_MAX_SIDE", "640")),
            worker_id=_env("ML_WORKER_ID", socket.gethostname()),
            load_threshold=float(_env("ML_LOAD_THRESHOLD", "0.7")),
            auto_neutral_s=float(_env("ML_AUTO_NEUTRAL_S", "0")),
        )
