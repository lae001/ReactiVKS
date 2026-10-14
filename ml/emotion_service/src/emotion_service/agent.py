"""Воркер LiveKit Agents (ADR-007): агент emotion-agent подключается к встрече как служебный участник.

Запуск для разработки: `emotion-agent dev` (переменные LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET).
meeting-service диспетчеризует агента в комнату: CreateDispatch(room, agent_name="emotion-agent", metadata={"fps": 3}).
"""

from __future__ import annotations

import json
import logging

from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli

from emotion_service.classifier import OnnxEmotionClassifier
from emotion_service.detection import YuNetDetector
from emotion_service.fusion import BlendshapeHead
from emotion_service.landmarks import FaceMeshAnalyzer
from emotion_service.pipeline import EmotionPipeline
from emotion_service.room import RoomAnalyzer
from emotion_service.sampling import AdaptiveRate
from emotion_service.settings import Settings
from emotion_service.sinks import LoggingSink
from emotion_service.smoothing import TemporalSmoother

AGENT_NAME = "emotion-agent"
log = logging.getLogger(__name__)


def prewarm(proc: JobProcess) -> None:
    """Модель загружается один раз на процесс задания, до назначения комнаты."""
    settings = Settings.from_env()
    proc.userdata["settings"] = settings
    proc.userdata["classifier"] = OnnxEmotionClassifier(settings.model_card, threads=settings.onnx_threads)
    # Голова по мимике лежит рядом с карточкой модели (ml/training/scripts/train_blendshape_head.py).
    head_path = settings.model_card.parent / "blendshape_head.json"
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
    classifier: OnnxEmotionClassifier = ctx.proc.userdata["classifier"]
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
        max_side=settings.max_side,
    )
    analyzer = RoomAnalyzer(
        ctx.room,
        pipeline,
        LoggingSink(),
        AdaptiveRate(target_fps=fps, min_fps=settings.min_fps, max_fps=settings.max_fps),
        worker_id=settings.worker_id,
        model_version=classifier.model_version,
    )
    ctx.add_shutdown_callback(analyzer.aclose)
    await analyzer.run()


def main() -> None:
    settings = Settings.from_env()
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
            load_threshold=settings.load_threshold,
        )
    )


if __name__ == "__main__":
    main()
