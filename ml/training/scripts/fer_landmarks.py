"""5 точек YuNet (глаза, нос, уголки рта) для всех изображений FER-2013 – для синтетических очков и бороды.

Изображение 48×48 увеличивается до 200 px в кадре 640×360 (как в calibrate_crop.py), точки переводятся обратно в
координаты 48×48. Не найдено – NaN (fer_training.occlusions подставит средний шаблон). Результат –
data/fer2013/landmarks.npz, ключи – сплиты, форма (N, 5, 2).

Запуск из ml/training:  uv run python scripts/fer_landmarks.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from emotion_service.detection import YuNetDetector

from fer_training.data import load_fer2013

MODELS = Path(__file__).absolute().parents[2] / "models"
SIDE, X0, Y0 = 200, 220, 80


def main() -> None:
    detector = YuNetDetector(MODELS / "yunet" / "face_detection_yunet_2023mar.onnx")
    out: dict[str, np.ndarray] = {}
    for split, data in load_fer2013(Path("data/fer2013")).items():
        points = np.full((len(data), 5, 2), np.nan, np.float32)
        for i, gray in enumerate(data.images):
            frame = np.full((360, 640, 3), 60, np.uint8)
            frame[Y0 : Y0 + SIDE, X0 : X0 + SIDE] = cv2.resize(gray, (SIDE, SIDE), interpolation=cv2.INTER_CUBIC)[
                :, :, None
            ]
            faces = detector.detect(frame)
            if faces and faces[0].landmarks is not None:
                points[i] = (faces[0].landmarks - np.array([X0, Y0])) * (gray.shape[0] / SIDE)
        print(f"{split}: точки найдены {np.mean(~np.isnan(points[:, 0, 0])):.3f}")
        out[split] = points
    np.savez_compressed("data/fer2013/landmarks.npz", **out)


if __name__ == "__main__":
    main()
