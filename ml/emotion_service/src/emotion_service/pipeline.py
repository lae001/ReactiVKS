"""Конвейер такта: детекция → кроп → пакетная классификация (+ мимика сетки лица) → сглаживание; внимание.

Синхронный и без ввода-вывода: агент вызывает его в пуле потоков (asyncio.to_thread), тесты – напрямую.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

from emotion_service.attention import Attention, AttentionTracker, HeadPose, head_pose, mesh_pose
from emotion_service.classifier import EmotionClassifier
from emotion_service.detection import FaceDetector
from emotion_service.fusion import BlendshapeHead
from emotion_service.landmarks import FaceMesh, FaceMeshAnalyzer
from emotion_service.preprocessing import FaceBox, align_crop, to_model_batch
from emotion_service.smoothing import TemporalSmoother

AnalysisState = Literal["analyzing", "no_face"]


@dataclass(frozen=True, slots=True)
class FaceResult:
    participant_id: str
    state: AnalysisState
    probs: dict[str, float] | None = None  # сглаженные
    raw_dominant: str | None = None
    dominant: str | None = None
    confidence: float | None = None
    face_box_area: float | None = None  # доля площади кадра
    attention: Attention | None = None
    # Только для отладки и демонстрации: в события не попадают (приватность – координаты и изображение лица).
    face: FaceBox | None = field(default=None, repr=False, compare=False)
    crop: np.ndarray | None = field(default=None, repr=False, compare=False)
    mesh: FaceMesh | None = field(default=None, repr=False, compare=False)  # координаты – в уменьшенном кадре
    cnn_probs: dict[str, float] | None = field(default=None, repr=False, compare=False)
    raw_probs: dict[str, float] | None = field(default=None, repr=False, compare=False)
    scale: float = field(default=1.0, repr=False, compare=False)  # кадр уменьшен в scale раз перед детекцией


class EmotionPipeline:
    def __init__(
        self,
        detector: FaceDetector,
        classifier: EmotionClassifier,
        smoother: TemporalSmoother | None = None,
        attention: AttentionTracker | None = None,
        mesh: FaceMeshAnalyzer | None = None,
        blendshape_head: BlendshapeHead | None = None,
        max_side: int = 640,
        min_face_px: int = 24,
    ) -> None:
        self.detector = detector
        self.classifier = classifier
        self.smoother = smoother or TemporalSmoother()
        self.attention = attention or AttentionTracker()
        self.mesh = mesh
        self.blendshape_head = blendshape_head
        self.max_side = max_side
        self.min_face_px = min_face_px

    def _downscale(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        scale = self.max_side / max(height, width)
        if scale >= 1:
            return image
        return cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)

    def process(self, frames: list[tuple[str, np.ndarray]], now: float) -> list[FaceResult]:
        """frames – (participant_id, RGB-кадр); now – монотонное время такта для сглаживания."""
        results: dict[str, FaceResult] = {}
        crops: list[np.ndarray] = []
        owners: list[tuple[str, float, FaceBox, float, FaceMesh | None]] = []
        for participant_id, rgb in frames:
            image = self._downscale(rgb)
            faces = [f for f in self.detector.detect(image) if min(f.w, f.h) >= self.min_face_px]
            if not faces:
                self.smoother.touch_missing(participant_id, now)
                attention = self.attention.update(participant_id, None, now)
                results[participant_id] = FaceResult(participant_id, "no_face", attention=attention)
                continue
            # В кадре участника анализируется крупнейшее лицо: это он сам, а не люди на фоне.
            face = faces[0]
            crops.append(align_crop(image, face))
            area = face.area / (image.shape[0] * image.shape[1])
            mesh = self.mesh.analyze(image, face) if self.mesh is not None else None
            owners.append((participant_id, area, face, rgb.shape[1] / image.shape[1], mesh))

        if crops:
            labels = self.classifier.labels
            probs = self.classifier.predict(to_model_batch(crops))
            for (participant_id, area, face, scale, mesh), crop, cnn in zip(owners, crops, probs, strict=True):
                raw = cnn
                if mesh is not None and self.blendshape_head is not None:
                    raw = self.blendshape_head.fuse(cnn, mesh.blendshape_vector())
                smoothed = self.smoother.update(participant_id, raw, now)
                pose: HeadPose | None
                if mesh is not None:
                    pose = mesh_pose(mesh.yaw_deg, mesh.pitch_deg, mesh.gaze_x)
                else:
                    pose = head_pose(face.landmarks) if face.landmarks is not None else None
                best = int(smoothed.argmax())
                results[participant_id] = FaceResult(
                    participant_id=participant_id,
                    state="analyzing",
                    probs={label: round(float(p), 4) for label, p in zip(labels, smoothed, strict=True)},
                    raw_dominant=labels[int(raw.argmax())],
                    dominant=labels[best],
                    confidence=round(float(smoothed[best]), 4),
                    face_box_area=round(area, 4),
                    attention=self.attention.update(participant_id, pose, now),
                    face=face,
                    crop=crop,
                    mesh=mesh,
                    cnn_probs={label: round(float(p), 4) for label, p in zip(labels, cnn, strict=True)},
                    raw_probs={label: round(float(p), 4) for label, p in zip(labels, raw, strict=True)},
                    scale=scale,
                )
        return [results[pid] for pid, _ in frames]
