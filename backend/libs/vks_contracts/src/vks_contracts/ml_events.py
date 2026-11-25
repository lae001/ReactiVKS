"""Топики ``ml.status`` и ``emotion.samples`` – производитель emotion-ml-service (напрямую, без БД), ключ –
``meeting_id``."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from vks_contracts.envelope import MeetingKeyed
from vks_contracts.topics import Topic

__all__ = [
    "EMOTIONS",
    "EMOTION_GROUPS",
    "Attention",
    "Behavior",
    "Emotion",
    "EmotionGroup",
    "EmotionGroupProbabilities",
    "EmotionProbabilities",
    "EmotionSample",
    "MlStatus",
    "group_probabilities",
]


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


EmotionGroup = Literal["joy", "surprise", "neutral", "discontent", "tension"]
# Группы для панели организатора и отчета (ADR-013): модель распознает 7 классов, организатор видит 5 групп –
# классы, которые модель путает между собой и которые на встрече значат одно и то же, объединены.
EMOTION_GROUPS: dict[EmotionGroup, tuple[Emotion, ...]] = {
    "joy": ("happy",),
    "surprise": ("surprise",),
    "neutral": ("neutral",),
    "discontent": ("angry", "disgust"),  # недовольство: гнев и отвращение (модель путает их в 24 % случаев)
    "tension": ("sad", "fear"),  # напряжение: грусть и страх (страх уходит в грусть в 20 % случаев)
}


class EmotionGroupProbabilities(BaseModel):
    """Вероятности 5 групп – суммы вероятностей их классов (сглаженные)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    joy: float = Field(ge=0, le=1)
    surprise: float = Field(ge=0, le=1)
    neutral: float = Field(ge=0, le=1)
    discontent: float = Field(ge=0, le=1)
    tension: float = Field(ge=0, le=1)


def group_probabilities(probs: EmotionProbabilities) -> EmotionGroupProbabilities:
    values = probs.model_dump()
    return EmotionGroupProbabilities(
        **{group: min(1.0, sum(values[e] for e in members)) for group, members in EMOTION_GROUPS.items()}
    )


class Behavior(BaseModel):
    """Поведенческие сигналы по сетке лица (не эмоции): кивки и покачивания головой, усталость (ADR-013)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    agreement: Literal["agree", "disagree", "none"] = Field(description="Кивает / качает головой / нет жеста")
    nod_score: float = Field(ge=0, le=1)
    shake_score: float = Field(ge=0, le=1)
    fatigue: Literal["alert", "tired"] | None = Field(default=None, description="None – мало данных (< 10 с)")
    fatigue_score: float | None = Field(default=None, ge=0, le=1)
    perclos: float | None = Field(default=None, ge=0, le=1, description="Доля времени с прикрытыми глазами за 30 с")
    yawns_per_min: float | None = Field(default=None, ge=0)
    speech: Literal["speaking", "silent", "side_talk"] | None = Field(
        default=None,
        description=(
            "По движению губ и уголков рта (звук не анализируется): speaking – говорит при включенном микрофоне, "
            "side_talk – говорит при выключенном микрофоне (с кем-то в комнате), silent – молчит; None – мало кадров"
        ),
    )
    mouth_activity: float | None = Field(default=None, ge=0, le=1, description="Активность рта за 2 с")
    mic_on: bool | None = Field(default=None, description="Микрофон включен (LiveKit); None – неизвестно")


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
    groups: EmotionGroupProbabilities | None = Field(
        default=None, description="Необязательное: 5 групп для панели (ADR-013); есть, когда есть probs"
    )
    dominant_group: EmotionGroup | None = None
    behavior: Behavior | None = Field(default=None, description="Необязательное: нужна сетка лица")

    @model_validator(mode="after")
    def _probabilities_only_while_analyzing(self) -> Self:
        """Вероятности есть ровно тогда, когда лицо анализируется: иначе панель показала бы эмоцию без лица."""
        if (self.state == "analyzing") != (self.probs is not None):
            raise ValueError("probs is present exactly when state is 'analyzing'")
        return self
