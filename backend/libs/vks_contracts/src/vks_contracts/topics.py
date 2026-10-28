"""Топики Kafka (events.md, «Топики»; создаются по deploy/kafka/topics.yaml)."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Topic"]


class Topic(StrEnum):
    EMOTION_SAMPLES = "emotion.samples"
    ML_STATUS = "ml.status"
    MEETING_EVENTS = "meeting.events"
    REPORT_EVENTS = "report.events"
    USER_EVENTS = "user.events"

    @property
    def dead_letters(self) -> str:
        """Топик недоставляемых сообщений потребителей этого топика."""
        return f"{self.value}.dlq"
