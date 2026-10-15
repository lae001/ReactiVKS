"""Анализ одной комнаты LiveKit: подписка на камеры участников с согласием, выборка кадров, такты конвейера.

Реакция на события комнаты – таблица «Реакция на согласие» в docs/ml/emotion-ml-service.md.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from livekit import rtc

from emotion_service.events import StateThrottle, emotion_sample, envelope, ml_status
from emotion_service.pipeline import EmotionPipeline
from emotion_service.sampling import AdaptiveRate, FrameSampler
from emotion_service.sinks import ResultSink

log = logging.getLogger(__name__)

SAMPLES_TOPIC = "emotion.samples"
STATUS_TOPIC = "ml.status"
HEARTBEAT_S = 5.0
IDENTITY_PREFIX = "p_"


def participant_id(participant: rtc.RemoteParticipant) -> str:
    identity = participant.identity
    return identity.removeprefix(IDENTITY_PREFIX)


def is_human(participant: rtc.RemoteParticipant) -> bool:
    return (
        participant.attributes.get("vks.kind", "human") != "agent"
        and participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
    )


def has_consent(participant: rtc.RemoteParticipant) -> bool:
    return participant.attributes.get("vks.consent") == "granted"


def is_camera(publication: rtc.TrackPublication) -> bool:
    return publication.kind == rtc.TrackKind.KIND_VIDEO and publication.source == rtc.TrackSource.SOURCE_CAMERA


def frame_to_rgb(frame: rtc.VideoFrame) -> np.ndarray:
    if frame.type != rtc.VideoBufferType.RGB24:
        frame = frame.convert(rtc.VideoBufferType.RGB24)
    return np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)


class RoomAnalyzer:
    def __init__(
        self,
        room: rtc.Room,
        pipeline: EmotionPipeline,
        sink: ResultSink,
        rate: AdaptiveRate,
        worker_id: str,
        model_version: str,
        auto_calibrate: bool = False,
    ) -> None:
        self.room = room
        self.meeting_id = room.name
        self.pipeline = pipeline
        self.sink = sink
        self.rate = rate
        self.worker_id = worker_id
        self.model_version = model_version
        # Автокалибровка: начало анализа участника считается его нейтральным лицом (ML_AUTO_NEUTRAL_S).
        self.auto_calibrate = auto_calibrate
        self.sampler: FrameSampler[rtc.VideoFrame] = FrameSampler()
        self._readers: dict[str, asyncio.Task[None]] = {}  # track sid → чтение дорожки
        self._throttle = StateThrottle()
        self._pending: list[dict[str, Any]] = []  # события состояний из обработчиков, уходят в ближайшем такте
        self._stopped = asyncio.Event()
        self._status = "active"
        self.ticks = 0
        self.faces_analyzed = 0

    # ------------------------------------------------------------------ события комнаты

    def attach(self) -> None:
        self.room.on("participant_connected", self._evaluate)
        self.room.on("participant_attributes_changed", self._on_attributes_changed)
        self.room.on("participant_disconnected", self._on_participant_disconnected)
        self.room.on("track_published", lambda pub, p: self._evaluate(p))
        self.room.on("track_subscribed", self._on_track_subscribed)
        self.room.on("track_unsubscribed", lambda track, pub, p: self._stop_reader(pub.sid))
        self.room.on("track_muted", self._on_track_muted)
        self.room.on("track_unmuted", lambda p, pub: self._evaluate(p))
        self.room.on("disconnected", lambda reason: self.stop())
        for participant in self.room.remote_participants.values():
            self._evaluate(participant)

    def _evaluate(self, participant: rtc.RemoteParticipant) -> None:
        """Подписка только на камеры участников с vks.consent = granted; иначе – отписка и состояние no_consent."""
        if not is_human(participant):
            return
        consent = has_consent(participant)
        for publication in participant.track_publications.values():
            if is_camera(publication) and isinstance(publication, rtc.RemoteTrackPublication):
                if publication.subscribed != consent:
                    publication.set_subscribed(consent)
                if not consent:
                    self._stop_reader(publication.sid)
        if not consent:
            self._reset(participant)
            self._queue_state(participant, "no_consent")

    def _on_attributes_changed(self, changed: dict[str, str], participant: rtc.RemoteParticipant) -> None:
        if "vks.consent" in changed:
            log.info("Согласие %s: %s", participant.identity, changed["vks.consent"])
            self._evaluate(participant)

    def _on_participant_disconnected(self, participant: rtc.RemoteParticipant) -> None:
        for publication in participant.track_publications.values():
            self._stop_reader(publication.sid)
        self._reset(participant)
        self._throttle.forget(participant_id(participant))

    def _on_track_subscribed(
        self, track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if not (isinstance(track, rtc.RemoteVideoTrack) and is_camera(publication) and has_consent(participant)):
            return
        if publication.sid not in self._readers:
            # Средний слой simulcast (≈ 640×360) достаточен для лица и экономит декодирование.
            publication.set_video_quality(rtc.VideoQuality.VIDEO_QUALITY_MEDIUM)
            log.info("Анализ камеры %s (%s)", participant.identity, publication.sid)
            pid = participant_id(participant)
            if self.auto_calibrate:
                self.pipeline.calibrator.start(pid)
            self._readers[publication.sid] = asyncio.create_task(self._read(track, pid))

    def _on_track_muted(self, participant: rtc.Participant, publication: rtc.TrackPublication) -> None:
        if isinstance(participant, rtc.RemoteParticipant) and is_camera(publication) and is_human(participant):
            self._reset(participant)
            if has_consent(participant):
                self._queue_state(participant, "camera_off")

    # ------------------------------------------------------------------ кадры

    async def _read(self, track: rtc.RemoteVideoTrack, pid: str) -> None:
        stream = rtc.VideoStream(track, format=rtc.VideoBufferType.RGB24)
        try:
            async for event in stream:
                self.sampler.put(pid, event.frame, time.monotonic())
        finally:
            await stream.aclose()

    def _stop_reader(self, track_sid: str) -> None:
        task = self._readers.pop(track_sid, None)
        if task is not None:
            task.cancel()

    def _reset(self, participant: rtc.RemoteParticipant) -> None:
        pid = participant_id(participant)
        self.sampler.remove(pid)
        self.pipeline.smoother.reset(pid)
        self.pipeline.attention.reset(pid)
        self.pipeline.calibrator.reset(pid)

    def _queue_state(self, participant: rtc.RemoteParticipant, state: str) -> None:
        pid = participant_id(participant)
        if self._throttle.should_publish(pid, state, time.monotonic()):
            payload = emotion_sample(self.meeting_id, pid, datetime.now(UTC), self.model_version, state=state)  # type: ignore[arg-type]
            self._pending.append(envelope("emotion.sample", payload))

    # ------------------------------------------------------------------ такты

    async def tick(self) -> int:
        """Один такт: последние кадры участников → конвейер → события. Возвращает число обработанных кадров."""
        samples = self.sampler.take()
        events, self._pending = self._pending, []
        if samples:
            now_mono, now_wall = time.monotonic(), datetime.now(UTC)
            frames = [(s.participant_id, frame_to_rgb(s.frame)) for s in samples]
            results = await asyncio.to_thread(self.pipeline.process, frames, now_mono)
            for sample, result in zip(samples, results, strict=True):
                if not self._throttle.should_publish(result.participant_id, result.state, now_mono):
                    continue
                received = now_wall - timedelta(seconds=now_mono - sample.received_at)
                payload = emotion_sample(self.meeting_id, result.participant_id, received, self.model_version, result)
                events.append(envelope("emotion.sample", payload))
                self.faces_analyzed += result.state == "analyzing"
        if events:
            await self.sink.publish(SAMPLES_TOPIC, self.meeting_id, events)
        self.ticks += 1
        return len(samples)

    async def _publish_status(self, state: str, effective_fps: float, reason: str | None = None) -> None:
        payload = ml_status(self.meeting_id, state, effective_fps, self.rate.target_fps, self.worker_id, reason)  # type: ignore[arg-type]
        await self.sink.publish(STATUS_TOPIC, self.meeting_id, [envelope("ml.status", payload)])

    async def run(self) -> None:
        """Такты до отключения от комнаты; ml.status – при старте, смене состояния и каждые 5 с."""
        self.attach()
        await self._publish_status("active", 0.0)
        last_beat, ticks_at_beat = time.monotonic(), 0
        while not self._stopped.is_set():
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:
                log.exception("Сбой такта анализа")
            elapsed = time.monotonic() - started
            self.rate.record(elapsed)

            status = "degraded" if self.rate.degraded else "active"
            since_beat = time.monotonic() - last_beat
            if status != self._status or since_beat >= HEARTBEAT_S:
                effective = (self.ticks - ticks_at_beat) / max(since_beat, 1e-6)
                reason = "overload" if status == "degraded" else None
                await self._publish_status(status, effective, reason)
                self._status = status
                last_beat, ticks_at_beat = time.monotonic(), self.ticks

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=max(0.0, self.rate.period - elapsed))
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    async def aclose(self, reason: str | None = None) -> None:
        self.stop()
        for sid in list(self._readers):
            self._stop_reader(sid)
        await self._publish_status("stopped", 0.0, reason)
