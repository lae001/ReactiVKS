"""Модульные тесты конвейера без LiveKit и без реальных моделей."""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from emotion_service.attention import AttentionTracker, head_pose, mesh_pose
from emotion_service.events import StateThrottle, emotion_sample, envelope, iso_now, ml_status, uuid7
from emotion_service.labels import LABELS
from emotion_service.pipeline import EmotionPipeline
from emotion_service.preprocessing import CROP_SIZE, FaceBox, align_crop, eye_angle, to_model_batch
from emotion_service.sampling import AdaptiveRate, FrameSampler
from emotion_service.smoothing import TemporalSmoother


class FixedDetector:
    def __init__(self, faces: dict[int, list[FaceBox]]) -> None:
        self.faces = faces  # ключ – ширина кадра, чтобы различать участников

    def detect(self, image: np.ndarray) -> list[FaceBox]:
        return self.faces.get(image.shape[1], [])


class FixedClassifier:
    labels = LABELS
    model_version = "test@0"

    def __init__(self, probs: np.ndarray) -> None:
        self.probs = probs
        self.calls: list[int] = []

    def predict(self, faces: np.ndarray) -> np.ndarray:
        assert faces.shape[1:] == (1, CROP_SIZE, CROP_SIZE)
        assert faces.dtype == np.float32 and 0 <= faces.min() and faces.max() <= 1
        self.calls.append(len(faces))
        return np.repeat(self.probs[None], len(faces), axis=0)


def one_hot(index: int) -> np.ndarray:
    probs = np.full(len(LABELS), 0.01, dtype=np.float32)
    probs[index] = 1 - 0.01 * (len(LABELS) - 1)
    return probs


# ---------------------------------------------------------------------------- препроцессинг


def test_eye_angle_is_symmetric_to_landmark_order() -> None:
    a = np.array([[10, 10], [30, 20], [0, 0], [0, 0], [0, 0]], dtype=np.float32)
    b = a.copy()
    b[[0, 1]] = b[[1, 0]]
    assert eye_angle(a) == pytest.approx(eye_angle(b)) == pytest.approx(26.565, abs=1e-3)


def test_align_crop_levels_eyes() -> None:
    # Темные «глаза» на светлом фоне, линия глаз наклонена на 20°.
    image = np.full((200, 200, 3), 220, dtype=np.uint8)
    angle = np.deg2rad(20)
    center = np.array([100.0, 100.0])
    offset = 30 * np.array([np.cos(angle), np.sin(angle)])
    eyes = [center - offset, center + offset]
    for x, y in eyes:
        image[int(y) - 4 : int(y) + 4, int(x) - 4 : int(x) + 4] = 0
    landmarks = np.array([eyes[0], eyes[1], center, center, center], dtype=np.float32)
    crop = align_crop(image, FaceBox(50, 50, 100, 100, 0.9, landmarks), margin=0.0, rotate=True)
    assert crop.shape == (CROP_SIZE, CROP_SIZE) and crop.dtype == np.uint8
    rows = np.flatnonzero(crop.min(axis=1) < 100)
    # После выравнивания оба глаза в одной полосе строк.
    assert rows.max() - rows.min() <= 4


def test_to_model_batch_shape_and_range() -> None:
    batch = to_model_batch([np.full((CROP_SIZE, CROP_SIZE), 255, np.uint8), np.zeros((CROP_SIZE, CROP_SIZE), np.uint8)])
    assert batch.shape == (2, 1, CROP_SIZE, CROP_SIZE)
    assert batch.max() == 1.0 and batch.min() == 0.0


# ---------------------------------------------------------------------------- выборка и частота


def test_sampler_keeps_only_latest_frame() -> None:
    sampler: FrameSampler[int] = FrameSampler()
    for i in range(30):
        sampler.put("a", i, float(i))
    sampler.put("b", 100, 0.0)
    taken = {s.participant_id: s.frame for s in sampler.take()}
    assert taken == {"a": 29, "b": 100}
    assert sampler.dropped == 29
    assert sampler.take() == []  # кадр не выдается дважды


def test_adaptive_rate_degrades_and_recovers() -> None:
    rate = AdaptiveRate(target_fps=4, min_fps=2, max_fps=5)
    for _ in range(5):
        rate.record(0.9 * rate.period)
    assert rate.fps == 3
    for _ in range(5):
        rate.record(0.9 * rate.period)
    assert rate.fps == 2 and not rate.degraded
    for _ in range(5):
        rate.record(0.9 * rate.period)
    assert rate.fps == 2 and rate.degraded
    for _ in range(10):
        rate.record(0.1 * rate.period)
    assert rate.fps == 3 and not rate.degraded


def test_adaptive_rate_validates_bounds() -> None:
    with pytest.raises(ValueError):
        AdaptiveRate(target_fps=1, min_fps=2)


# ---------------------------------------------------------------------------- сглаживание


def test_smoother_ema_and_reset_after_gap() -> None:
    smoother = TemporalSmoother(alpha=0.4, reset_after_s=3)
    first = smoother.update("a", one_hot(0), 0.0)
    second = smoother.update("a", one_hot(3), 0.3)
    assert second[3] == pytest.approx(0.4 * one_hot(3)[3] + 0.6 * first[3])
    assert second.argmax() == 0  # одна смена кадра не перебивает устойчивую эмоцию
    after_gap = smoother.update("a", one_hot(3), 10.0)
    assert after_gap.argmax() == 3


# ---------------------------------------------------------------------------- конвейер


def test_pipeline_batches_faces_and_reports_no_face() -> None:
    face = FaceBox(100, 50, 120, 120, 0.95, None)
    detector = FixedDetector({640: [face], 320: []})
    classifier = FixedClassifier(one_hot(3))
    pipeline = EmotionPipeline(detector, classifier)
    frames = [
        ("p1", np.zeros((360, 640, 3), np.uint8)),
        ("p2", np.zeros((180, 320, 3), np.uint8)),
        ("p3", np.zeros((360, 640, 3), np.uint8)),
    ]
    results = pipeline.process(frames, now=0.0)
    assert [r.participant_id for r in results] == ["p1", "p2", "p3"]
    assert classifier.calls == [2]  # один пакет на такт
    assert results[0].state == "analyzing" and results[0].dominant == "happy"
    assert results[0].probs is not None and set(results[0].probs) == set(LABELS)
    assert results[0].face_box_area == pytest.approx(120 * 120 / (640 * 360), abs=1e-4)
    assert results[1].state == "no_face" and results[1].probs is None


def test_pipeline_downscales_large_frames_and_ignores_tiny_faces() -> None:
    detector = FixedDetector({640: [FaceBox(0, 0, 10, 10, 0.9, None)]})
    pipeline = EmotionPipeline(detector, FixedClassifier(one_hot(0)), max_side=640, min_face_px=24)
    (result,) = pipeline.process([("p", np.zeros((720, 1280, 3), np.uint8))], now=0.0)
    assert result.state == "no_face"


# ---------------------------------------------------------------------------- события


def test_uuid7_version_and_order() -> None:
    first, second = uuid7(), uuid7()
    assert first.version == 7 and first.variant == uuid.RFC_4122
    assert first.int >> 80 <= second.int >> 80


MEETING = "0192f1c4-0000-7000-8000-000000000001"
PARTICIPANT = "0192f1c4-0000-7000-8000-000000000002"


def test_emotion_sample_matches_contract() -> None:
    from datetime import UTC, datetime

    from vks_contracts.envelope import EventEnvelope
    from vks_contracts.ml_events import EmotionSample

    face = FaceBox(100, 50, 120, 120, 0.95, None)
    pipeline = EmotionPipeline(FixedDetector({640: [face]}), FixedClassifier(one_hot(6)))
    (result,) = pipeline.process([(PARTICIPANT, np.zeros((360, 640, 3), np.uint8))], now=0.0)
    sample = emotion_sample(MEETING, PARTICIPANT, datetime(2026, 11, 20, 7, 12, 3, 643000, tzinfo=UTC), "t@0", result)
    assert isinstance(sample, EmotionSample) and sample.key() == MEETING
    assert sample.dominant == "neutral" and sample.state == "analyzing" and sample.probs is not None
    assert sample.attention is not None and sample.attention.state == "attentive"
    off = emotion_sample(MEETING, PARTICIPANT, datetime.now(UTC), "t@0", state="camera_off")
    assert off.state == "camera_off" and off.probs is None and off.attention is None
    event = envelope(sample)
    assert isinstance(event, EventEnvelope) and event.producer == "emotion-ml-service" and event.version == 1
    assert event.event_id.version == 7 and event.payload["ts"] == "2026-11-20T07:12:03.643000Z"
    assert iso_now().endswith("Z")


def test_ml_status_target_fps_is_integer_per_contract() -> None:
    status = ml_status(MEETING, "active", 2.96, 3.0, "w1")
    assert status.target_fps == 3 and status.effective_fps == 2.96


async def test_kafka_sink_sends_contract_messages_and_counts_failures() -> None:
    import asyncio
    import json

    from emotion_service.sinks import KafkaSink

    class FakeProducer:
        def __init__(self) -> None:
            self.messages: list[tuple[str, bytes, bytes, list[tuple[str, bytes]]]] = []
            self.fail_next = False

        async def start(self) -> None: ...

        async def stop(self) -> None: ...

        async def send(self, topic: str, value: bytes, key: bytes, headers: list[tuple[str, bytes]]) -> asyncio.Future:
            if self.fail_next:
                raise RuntimeError("buffer full")
            self.messages.append((topic, key, value, headers))
            future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
            future.set_result(object())
            return future

    producer = FakeProducer()
    sink = KafkaSink("unused", producer=producer)
    await sink.publish([ml_status(MEETING, "active", 3.0, 3, "w1")])
    producer.fail_next = True
    await sink.publish([ml_status(MEETING, "active", 3.0, 3, "w1")])
    await asyncio.sleep(0)
    topic, key, value, headers = producer.messages[0]
    assert topic == "ml.status" and key == MEETING.encode()
    assert json.loads(value)["type"] == "ml.status" and dict(headers)["event_type"] == b"ml.status"
    assert sink.sent == 1 and sink.errors == 1


def test_state_throttle_rules() -> None:
    throttle = StateThrottle(no_face_interval_s=1.0)
    assert throttle.should_publish("p", "no_consent", 0.0)
    assert not throttle.should_publish("p", "no_consent", 5.0)  # только при смене состояния
    assert throttle.should_publish("p", "no_face", 5.1)
    assert not throttle.should_publish("p", "no_face", 5.5)  # не чаще 1 раза в секунду
    assert throttle.should_publish("p", "no_face", 6.2)
    assert throttle.should_publish("p", "analyzing", 6.3)
    assert throttle.should_publish("p", "analyzing", 6.4)


# ---------------------------------------------------------------------------- внимание


def test_head_pose_frontal_turned_and_tilted() -> None:
    frontal = head_pose(np.array([[30, 40], [70, 40], [50, 62.4], [35, 80], [65, 80]], float))
    assert frontal is not None and frontal.looking and frontal.source == "landmarks5"
    assert frontal.yaw_deg == pytest.approx(0.0)
    turned = head_pose(np.array([[30, 40], [70, 40], [64, 62.4], [35, 80], [65, 80]], float))
    assert turned is not None and not turned.looking and turned.yaw_deg == pytest.approx(44.4, abs=0.1)
    down = head_pose(np.array([[30, 40], [70, 40], [50, 72], [35, 80], [65, 80]], float))
    assert down is not None and not down.looking
    # Наклон головы (roll) не меняет оценку: точки повернуты на 30°.
    angle = np.deg2rad(30)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    rolled = head_pose(np.array([[30, 40], [70, 40], [50, 62.4], [35, 80], [65, 80]], float) @ rot.T)
    assert rolled is not None and rolled.looking and rolled.yaw_deg == pytest.approx(0.0, abs=1e-6)


def test_attention_engaged_after_long_look_distracted_quickly() -> None:
    tracker = AttentionTracker()
    look, away = mesh_pose(0.0, 0.0, 0.0), mesh_pose(40.0, 0.0, 0.0)
    states = [tracker.update("p", look, t / 3).state for t in range(0, 3 * 6)]
    assert states[0] == "attentive" and states[3 * 4] == "attentive" and states[-1] == "engaged"
    first_engaged = states.index("engaged") / 3
    assert 4.0 <= first_engaged <= 5.0
    t0 = 6.0
    away_states = [tracker.update("p", away, t0 + t / 3).state for t in range(1, 3 * 4)]
    first_distracted = (away_states.index("distracted") + 1) / 3
    assert 1.5 <= first_distracted <= 3.0
    attention = tracker.update("p", None, t0 + 5)  # лицо пропало – тоже отвлечение
    assert attention.state == "distracted" and not attention.looking
    assert 0.0 <= attention.interest <= 1.0


def test_pipeline_reports_attention_for_no_face() -> None:
    pipeline = EmotionPipeline(FixedDetector({}), FixedClassifier(one_hot(0)))
    (result,) = pipeline.process([("p", np.zeros((360, 640, 3), np.uint8))], now=0.0)
    assert result.state == "no_face" and result.attention is not None and not result.attention.looking


def test_mesh_pose_uses_gaze() -> None:
    assert mesh_pose(5.0, -5.0, 0.1).looking
    assert not mesh_pose(5.0, -5.0, 0.8).looking  # голова прямо, глаза в сторону
    assert not mesh_pose(5.0, 35.0, None).looking


# ---------------------------------------------------------------------------- калибровка


def test_calibration_maps_personal_neutral_to_neutral_and_keeps_changes() -> None:
    from emotion_service.calibration import NEUTRAL_TARGET, NeutralCalibrator

    calibrator = NeutralCalibrator(duration_s=1.0, min_samples=3)
    resting = np.array([0.05, 0.02, 0.08, 0.05, 0.55, 0.05, 0.20])  # спокойное лицо, но модель говорит sad
    smiling = np.array([0.03, 0.01, 0.04, 0.60, 0.17, 0.05, 0.10])
    unchanged, _ = calibrator.apply("p", resting, 0.0)
    assert unchanged is resting  # без запуска калибровки – без изменений
    calibrator.start("p")
    done = [calibrator.apply("p", resting, t / 4)[1] for t in range(6)]
    assert done.index(True) == 4 and calibrator.status("p", 1.5).state == "ready"
    after, _ = calibrator.apply("p", resting, 2.0)
    assert LABELS[int(after.argmax())] == "neutral" and after.max() == pytest.approx(NEUTRAL_TARGET, abs=1e-3)
    smile, _ = calibrator.apply("p", smiling, 2.3)
    assert LABELS[int(smile.argmax())] == "happy"
    calibrator.reset("p")
    assert calibrator.status("p", 3.0).state == "none"


def test_pipeline_resets_smoothing_when_calibration_completes() -> None:
    face = FaceBox(100, 50, 120, 120, 0.95, None)
    sad = np.array([0.05, 0.02, 0.08, 0.05, 0.55, 0.05, 0.20], np.float32)
    pipeline = EmotionPipeline(FixedDetector({640: [face]}), FixedClassifier(sad))
    frame = [("p", np.zeros((360, 640, 3), np.uint8))]
    assert pipeline.process(frame, 0.0)[0].dominant == "sad"
    pipeline.calibrator.start("p")
    results = [pipeline.process(frame, 0.1 + t * 0.4)[0] for t in range(12)]
    assert results[-1].calibration is not None and results[-1].calibration.state == "ready"
    assert results[-1].dominant == "neutral"


# ---------------------------------------------------------------------------- очки и борода


def test_condition_and_masking_of_occluded_zones() -> None:
    from emotion_service.fusion import BlendshapeHead, condition_of
    from emotion_service.landmarks import BLENDSHAPE_NAMES

    assert condition_of(()) == "none" and condition_of(("beard", "glasses")) == "glasses_beard"
    n = len(BLENDSHAPE_NAMES)
    head = BlendshapeHead(
        names=BLENDSHAPE_NAMES, mean=np.full(n, 0.1, np.float32), std=np.ones(n, np.float32),
        coef=np.zeros((7, n), np.float32), intercept=np.zeros(7, np.float32), weight=0.3,
        weights={"none": 0.3, "glasses": 0.1, "beard": 0.0, "glasses_beard": 0.0},
    )  # fmt: skip
    features = np.ones(n, np.float32)
    masked = head.mask(features, ("glasses",))
    names = dict(zip(BLENDSHAPE_NAMES, masked, strict=True))
    assert names["eyeWideLeft"] == pytest.approx(0.1) and names["browInnerUp"] == pytest.approx(0.1)
    assert names["jawOpen"] == 1.0 and names["mouthSmileLeft"] == 1.0
    beard = dict(zip(BLENDSHAPE_NAMES, head.mask(features, ("beard",)), strict=True))
    assert beard["jawOpen"] == pytest.approx(0.1) and beard["mouthSmileLeft"] == pytest.approx(0.1)
    assert beard["eyeWideLeft"] == 1.0
    # Вес 0 для бороды – результат равен ответу CNN.
    cnn = one_hot(5)
    assert np.allclose(head.fuse_with_attributes(cnn, features, ("beard",)), cnn / cnn.sum(), atol=1e-5)


def test_routed_classifier_uses_robust_model_for_occluded_faces() -> None:
    from emotion_service.classifier import RoutedClassifier

    base, robust = FixedClassifier(one_hot(4)), FixedClassifier(one_hot(6))
    robust.model_version = "emotion-x@1.1.0"
    base.model_version = "emotion-x@1.0.0"
    routed = RoutedClassifier(base, robust)
    faces = np.zeros((2, 1, CROP_SIZE, CROP_SIZE), np.float32)
    probs = routed.predict(faces, np.array([False, True]))
    assert probs[0] == pytest.approx((one_hot(4) + one_hot(6)) / 2)
    assert probs[1] == pytest.approx(one_hot(6))
    assert routed.model_version == "emotion-x@1.1.0+1.0.0"
    assert base.calls == [1]  # базовая модель считается только для лиц без очков и бороды


def test_parallel_pipeline_matches_sequential() -> None:
    face = FaceBox(100, 50, 120, 120, 0.95, None)
    frames = [(f"p{i}", np.zeros((360, 640 if i % 3 else 320, 3), np.uint8)) for i in range(7)]

    def build(workers: int) -> EmotionPipeline:
        return EmotionPipeline(
            FixedDetector({640: [face]}), FixedClassifier(one_hot(3)), workers=workers,
            detector_factory=lambda: FixedDetector({640: [face]}),
        )  # fmt: skip

    sequential = build(1).process(frames, 0.0)
    parallel = build(3).process(frames, 0.0)
    assert [(r.participant_id, r.state, r.dominant) for r in sequential] == [
        (r.participant_id, r.state, r.dominant) for r in parallel
    ]
    assert [r.state for r in parallel].count("no_face") == 3
