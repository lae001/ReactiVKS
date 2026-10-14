"""Мимические коэффициенты MediaPipe Face Landmarker (52 blendshapes) для всех изображений FER-2013.

Изображение 48×48 увеличивается до 192 px с полями – так же, как кроп лица из кадра в сервисе подается в
FaceMeshAnalyzer. Если лицо не найдено, строка – NaN. Результат – data/fer2013/blendshapes.npz:
<сплит> – коэффициенты, <сплит>_pose – yaw, pitch, взгляд x, y.

Запуск из ml/training:  uv run python scripts/extract_blendshapes.py
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from emotion_service.landmarks import BLENDSHAPE_NAMES, FaceMeshAnalyzer

from fer_training.data import load_fer2013

MODELS = Path(__file__).absolute().parents[2] / "models"


def main() -> None:
    analyzer = FaceMeshAnalyzer(MODELS / "mediapipe" / "face_landmarker.task")
    out: dict[str, np.ndarray] = {}
    for split, data in load_fer2013(Path("data/fer2013")).items():
        started = time.perf_counter()
        features = np.full((len(data), len(BLENDSHAPE_NAMES)), np.nan, dtype=np.float32)
        pose = np.full((len(data), 4), np.nan, dtype=np.float32)  # yaw, pitch, gaze_x, gaze_y
        for i, gray in enumerate(data.images):
            mesh = analyzer.analyze_crop(np.repeat(gray[:, :, None], 3, axis=2))
            if mesh is not None:
                features[i] = mesh.blendshape_vector()
                pose[i] = [mesh.yaw_deg, mesh.pitch_deg, np.nan if mesh.gaze_x is None else mesh.gaze_x,
                           np.nan if mesh.gaze_y is None else mesh.gaze_y]  # fmt: skip
        found = ~np.isnan(features[:, 0])
        print(f"{split}: лицо найдено {found.mean():.3f}, {time.perf_counter() - started:.0f} с")
        out[split] = features
        out[f"{split}_pose"] = pose
    np.savez_compressed("data/fer2013/blendshapes.npz", **out)


if __name__ == "__main__":
    main()
