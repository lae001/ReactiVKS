"""Конвейер такта: детекция → кроп → пакетная классификация (+ мимика сетки лица) → сглаживание; внимание.

Синхронный и без ввода-вывода: агент вызывает его в пуле потоков (asyncio.to_thread), тесты – напрямую.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from vks_contracts.ml_events import EMOTION_GROUPS

from emotion_service.attention import Attention, AttentionTracker, HeadPose, head_pose, mesh_pose
from emotion_service.attributes import AttributeDetector, FaceAttributes
from emotion_service.behavior import Behavior, BehaviorTracker
from emotion_service.calibration import CalibrationStatus, NeutralCalibrator
from emotion_service.classifier import EmotionClassifier, RoutedClassifier
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
    groups: dict[str, float] | None = None  # 5 групп для панели (ADR-013), суммы сглаженных вероятностей
    dominant_group: str | None = None
    behavior: Behavior | None = None  # кивки / покачивания, усталость – нужна сетка лица
    attributes: FaceAttributes | None = field(default=None, compare=False)  # очки / борода; в события не уходят
    # Только для отладки и демонстрации: в события не попадают (приватность – координаты и изображение лица).
    face: FaceBox | None = field(default=None, repr=False, compare=False)
    crop: np.ndarray | None = field(default=None, repr=False, compare=False)
    mesh: FaceMesh | None = field(default=None, repr=False, compare=False)  # координаты – в уменьшенном кадре
    cnn_probs: dict[str, float] | None = field(default=None, repr=False, compare=False)
    raw_probs: dict[str, float] | None = field(default=None, repr=False, compare=False)  # после калибровки
    uncalibrated_probs: dict[str, float] | None = field(default=None, repr=False, compare=False)
    calibration: CalibrationStatus | None = field(default=None, repr=False, compare=False)
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
        calibrator: NeutralCalibrator | None = None,
        attribute_detector: AttributeDetector | None = None,
        behavior: BehaviorTracker | None = None,
        max_side: int = 640,
        min_face_px: int = 24,
        workers: int = 1,
        detector_factory: Callable[[], FaceDetector] | None = None,
        mesh_factory: Callable[[], FaceMeshAnalyzer] | None = None,
    ) -> None:
        self.detector = detector
        self.classifier = classifier
        self.smoother = smoother or TemporalSmoother()
        self.attention = attention or AttentionTracker()
        self.mesh = mesh
        self.blendshape_head = blendshape_head
        self.calibrator = calibrator or NeutralCalibrator()
        self.attribute_detector = attribute_detector
        self.behavior = behavior or BehaviorTracker()
        self.max_side = max_side
        self.min_face_px = min_face_px
        # Лица участников обрабатываются параллельно (детекция и сетка – C++ без GIL): у каждого потока свои
        # детектор и сетка – эти объекты не потокобезопасны (нагрузочный замер, load-test.md).
        self._factories = (detector_factory, mesh_factory)
        self._local = threading.local()
        self._pool = (
            ThreadPoolExecutor(workers, thread_name_prefix="face") if workers > 1 and detector_factory else None
        )

    def _thread_models(self) -> tuple[FaceDetector, FaceMeshAnalyzer | None]:
        if self._pool is None:
            return self.detector, self.mesh
        models: tuple[FaceDetector, FaceMeshAnalyzer | None] | None = getattr(self._local, "models", None)
        if models is None:
            detector_factory, mesh_factory = self._factories
            detector = detector_factory() if detector_factory is not None else self.detector
            mesh = mesh_factory() if mesh_factory is not None and self.mesh is not None else None
            models = (detector, mesh)
            self._local.models = models
        return models

    def _analyze_face(self, rgb: np.ndarray) -> tuple[np.ndarray, FaceBox | None, np.ndarray | None, FaceMesh | None]:
        """Детекция, кроп и сетка одного кадра – в потоке пула."""
        detector, mesh_analyzer = self._thread_models()
        image = self._downscale(rgb)
        faces = [f for f in detector.detect(image) if min(f.w, f.h) >= self.min_face_px]
        if not faces:
            return image, None, None, None
        # В кадре участника анализируется крупнейшее лицо: это он сам, а не люди на фоне.
        face = faces[0]
        mesh = mesh_analyzer.analyze(image, face) if mesh_analyzer is not None else None
        return image, face, align_crop(image, face), mesh

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
        owners: list[tuple[str, float, FaceBox, float, FaceMesh | None, FaceAttributes | None]] = []
        rgbs = [rgb for _, rgb in frames]
        analyzed = (
            list(self._pool.map(self._analyze_face, rgbs)) if self._pool else [self._analyze_face(f) for f in rgbs]
        )
        for (participant_id, rgb), (image, face, crop, mesh) in zip(frames, analyzed, strict=True):
            if face is None or crop is None:
                self.smoother.touch_missing(participant_id, now)
                attention = self.attention.update(participant_id, None, now)
                results[participant_id] = FaceResult(participant_id, "no_face", attention=attention)
                continue
            crops.append(crop)
            area = face.area / (image.shape[0] * image.shape[1])
            attributes = (
                self.attribute_detector.update(participant_id, image, face, now) if self.attribute_detector else None
            )
            owners.append((participant_id, area, face, rgb.shape[1] / image.shape[1], mesh, attributes))

        if crops:
            labels = self.classifier.labels
            batch = to_model_batch(crops)
            if isinstance(self.classifier, RoutedClassifier):
                occluded_mask = np.array([bool(o[5] and o[5].occluded) for o in owners])
                probs = self.classifier.predict(batch, occluded_mask if self.attribute_detector else None)
            else:
                probs = self.classifier.predict(batch)
            for (participant_id, area, face, scale, mesh, attributes), crop, cnn in zip(
                owners, crops, probs, strict=True
            ):
                raw = cnn
                if mesh is not None and self.blendshape_head is not None:
                    occluded = attributes.occluded if attributes is not None else ()
                    raw = self.blendshape_head.fuse_with_attributes(cnn, mesh.blendshape_vector(), occluded)
                uncalibrated = raw
                raw, calibrated_now = self.calibrator.apply(participant_id, raw, now)
                if calibrated_now:
                    self.smoother.reset(participant_id)  # сглаживание не тянет состояние до калибровки
                smoothed = self.smoother.update(participant_id, raw, now)
                pose: HeadPose | None
                if mesh is not None:
                    pose = mesh_pose(mesh.yaw_deg, mesh.pitch_deg, mesh.gaze_x)
                else:
                    pose = head_pose(face.landmarks) if face.landmarks is not None else None
                best = int(smoothed.argmax())
                probs_by_label = dict(zip(labels, (float(p) for p in smoothed), strict=True))
                groups: dict[str, float] = {
                    group: round(min(1.0, sum(probs_by_label[e] for e in members)), 4)
                    for group, members in EMOTION_GROUPS.items()
                }
                glasses = attributes is not None and attributes.glasses
                results[participant_id] = FaceResult(
                    participant_id=participant_id,
                    state="analyzing",
                    probs={label: round(float(p), 4) for label, p in zip(labels, smoothed, strict=True)},
                    raw_dominant=labels[int(raw.argmax())],
                    dominant=labels[best],
                    confidence=round(float(smoothed[best]), 4),
                    face_box_area=round(area, 4),
                    attention=self.attention.update(participant_id, pose, now),
                    attributes=attributes,
                    groups=groups,
                    dominant_group=max(groups, key=lambda g: groups[g]),
                    behavior=self.behavior.update(participant_id, mesh, now, glasses=glasses),
                    face=face,
                    crop=crop,
                    mesh=mesh,
                    cnn_probs={label: round(float(p), 4) for label, p in zip(labels, cnn, strict=True)},
                    raw_probs={label: round(float(p), 4) for label, p in zip(labels, raw, strict=True)},
                    uncalibrated_probs={
                        label: round(float(p), 4) for label, p in zip(labels, uncalibrated, strict=True)
                    },
                    calibration=self.calibrator.status(participant_id, now),
                    scale=scale,
                )
        return [results[pid] for pid, _ in frames]
