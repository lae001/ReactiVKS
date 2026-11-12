"""Воркер LiveKit Agents (ADR-007): агент emotion-agent подключается к встрече как служебный участник.

Запуск для разработки: `emotion-agent dev` (переменные LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET).
meeting-service диспетчеризует агента в комнату: CreateDispatch(room, agent_name="emotion-agent", metadata={"fps": 3}).
"""

from __future__ import annotations

import json
import logging

from livekit.agents import AutoSubscribe, JobContext, JobExecutorType, JobProcess, WorkerOptions, cli

from emotion_service.attributes import AttributeDetector
from emotion_service.calibration import NeutralCalibrator
from emotion_service.classifier import OnnxEmotionClassifier, RoutedClassifier
from emotion_service.detection import YuNetDetector
from emotion_service.fusion import BlendshapeHead
from emotion_service.landmarks import FaceMeshAnalyzer
from emotion_service.pipeline import EmotionPipeline
from emotion_service.room import RoomAnalyzer
from emotion_service.sampling import AdaptiveRate
from emotion_service.settings import Settings
from emotion_service.sinks import KafkaSink, LoggingSink, ResultSink
from emotion_service.smoothing import TemporalSmoother

AGENT_NAME = "emotion-agent"
log = logging.getLogger(__name__)


def prewarm(proc: JobProcess) -> None:
    """Модель загружается один раз на процесс задания, до назначения комнаты."""
    settings = Settings.from_env()
    proc.userdata["settings"] = settings
    base = OnnxEmotionClassifier(settings.model_card, threads=settings.onnx_threads)
    proc.userdata["classifier"] = (
        RoutedClassifier(base, OnnxEmotionClassifier(settings.robust_model_card, threads=settings.onnx_threads))
        if settings.robust_model_card
        else base
    )
    # Голова по мимике лежит рядом с карточкой модели (ml/training/scripts/train_blendshape_head.py).
    head_path = (settings.robust_model_card or settings.model_card).parent / "blendshape_head.json"
    proc.userdata["blendshape_head"] = (
        BlendshapeHead.load(head_path) if head_path.exists() and settings.face_mesh_model else None
    )


def target_fps(metadata: str | None, settings: Settings) -> float:
    try:
        requested = float(json.loads(metadata or "{}").get("fps", settings.target_fps))
    except (ValueError, TypeError, AttributeError):
        requested = settings.target_fps
    return min(max(requested, settings.min_fps), settings.max_fps)


async def entrypoint(ctx: JobContext) -> None:
    settings: Settings = ctx.proc.userdata["settings"]
    classifier: OnnxEmotionClassifier | RoutedClassifier = ctx.proc.userdata["classifier"]
    fps = target_fps(ctx.job.metadata, settings)

    # Подписка вручную: только камеры участников с согласием.
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE)
    await ctx.room.local_participant.set_attributes({"vks.kind": "agent"})
    log.info("Агент в комнате %s, целевая частота %.1f кадр/с", ctx.room.name, fps)

    pipeline = EmotionPipeline(
        YuNetDetector(settings.detector_model),
        classifier,
        TemporalSmoother(alpha=settings.ema_alpha),
        mesh=FaceMeshAnalyzer(settings.face_mesh_model) if settings.face_mesh_model else None,
        blendshape_head=ctx.proc.userdata["blendshape_head"],
        calibrator=NeutralCalibrator(auto_s=settings.auto_neutral_s or 5.0),
        attribute_detector=AttributeDetector(settings.attributes_card) if settings.attributes_card else None,
        max_side=settings.max_side,
        workers=settings.face_workers,
        detector_factory=lambda: YuNetDetector(settings.detector_model),
        mesh_factory=(lambda: FaceMeshAnalyzer(mesh_model)) if (mesh_model := settings.face_mesh_model) else None,
    )
    sink: ResultSink
    if settings.kafka_bootstrap:
        kafka = KafkaSink(settings.kafka_bootstrap, client_id=f"emotion-ml-service-{settings.worker_id}")
        await kafka.start()
        sink = kafka
    else:
        sink = LoggingSink()
    analyzer = RoomAnalyzer(
        ctx.room,
        pipeline,
        sink,
        AdaptiveRate(target_fps=fps, min_fps=settings.min_fps, max_fps=settings.max_fps),
        worker_id=settings.worker_id,
        model_version=classifier.model_version,
        auto_calibrate=settings.auto_neutral_s > 0,
    )

    async def shutdown(reason: str) -> None:
        await analyzer.aclose(reason)
        await sink.aclose()

    ctx.add_shutdown_callback(shutdown)
    await analyzer.run()


def main() -> None:
    settings = Settings.from_env()
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
            load_threshold=settings.load_threshold,
            # Процесс на встречу (ADR-007, emotion-ml-service.md): сбой или зависание одной встречи не задевает
            # другие. В потоковом режиме (по умолчанию в livekit-agents 1.8) два конвейера с MediaPipe в одном
            # процессе зависали – нагрузочный замер 2 × 10, load-test.md.
            job_executor_type=JobExecutorType.PROCESS,
            num_idle_processes=settings.idle_processes,
        )
    )


if __name__ == "__main__":
    main()
