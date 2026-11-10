"""Топики ``ml.status`` и ``emotion.samples`` – производитель emotion-ml-service (напрямую, без БД), ключ –
``meeting_id``."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from vks_contracts.envelope import MeetingKeyed
from vks_contracts.topics import Topic

__all__ = ["EMOTIONS", "Attention", "Emotion", "EmotionProbabilities", "EmotionSample", "MlStatus"]


class MlStatus(MeetingKeyed):
    """Состояние анализа встречи: при старте и остановке задания, при смене состояния и каждые 5 с."""

    event_type = "ml.status"
    topic = Topic.ML_STATUS

    state: Literal["active", "degraded", "stopped"]
    effective_fps: float = Field(ge=0)
    target_fps: int = Field(ge=2, le=5)
    worker_id: str
    reason: str | None = None


Emotion = Literal["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
EMOTIONS: tuple[Emotion, ...] = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


class EmotionProbabilities(BaseModel):
    """Сглаженные вероятности 7 классов."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    angry: float = Field(ge=0, le=1)
    disgust: float = Field(ge=0, le=1)
    fear: float = Field(ge=0, le=1)
    happy: float = Field(ge=0, le=1)
    sad: float = Field(ge=0, le=1)
    surprise: float = Field(ge=0, le=1)
    neutral: float = Field(ge=0, le=1)


class Attention(BaseModel):
    """Внимание участника по позе головы, взгляду и времени (не эмоция): engaged – смотрит в камеру ≈ 5 с,
    distracted – отвернулся, отвел взгляд или вышел из кадра ≈ 2,5 с (ml/emotion_service/.../attention.py)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    state: Literal["engaged", "attentive", "distracted"]
    interest: float = Field(ge=0, le=1, description="Заинтересованность; отвлеченность = 1 − interest")
    looking: bool = Field(description="Голова и взгляд направлены в камеру на этом кадре")
    yaw_deg: float | None = None
    pitch_deg: float | None = None
    gaze_x: float | None = Field(default=None, description="Положение радужки в глазу: −1 … 1, 0 – по центру")
    source: Literal["mesh", "landmarks5"] | None = None


class EmotionSample(MeetingKeyed):
    """Отсчет распознавания по одному участнику. Без координат лица и без кадров (ADR-009)."""

    event_type = "emotion.sample"
    topic = Topic.EMOTION_SAMPLES

    participant_id: UUID
    ts: AwareDatetime = Field(description="Время получения кадра сервисом")
    state: Literal["analyzing", "no_face", "camera_off", "no_consent"]
    probs: EmotionProbabilities | None
    raw_dominant: Emotion | None = Field(default=None, description="До сглаживания – для отладки качества")
    dominant: Emotion | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    face_box_area: float | None = Field(default=None, ge=0, le=1, description="Доля площади кадра")
    model_version: str
    attention: Attention | None = Field(
        default=None, description="Необязательное (без смены version); null у no_consent и camera_off"
    )

    @model_validator(mode="after")
    def _probabilities_only_while_analyzing(self) -> Self:
        """Вероятности есть ровно тогда, когда лицо анализируется: иначе панель показала бы эмоцию без лица."""
        if (self.state == "analyzing") != (self.probs is not None):
            raise ValueError("probs is present exactly when state is 'analyzing'")
        return self
