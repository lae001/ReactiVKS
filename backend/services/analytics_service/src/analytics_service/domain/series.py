"""Отсчеты, посекундные корзины и точки ряда."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

type Resolution = Literal["1s", "5s", "30s"]
RESOLUTION_SECONDS: dict[Resolution, int] = {"1s": 1, "5s": 5, "30s": 30}
PROBABILITY_COUNT = 7


@dataclass(frozen=True, slots=True)
class Sample:
    meeting_id: UUID
    participant_id: UUID
    ts: datetime
    probabilities: tuple[float, ...] | None
    model_version: str


@dataclass(frozen=True, slots=True)
class BufferedSample:
    offset: int
    received_at: datetime
    sample: Sample | None


@dataclass(frozen=True, slots=True)
class Bucket:
    meeting_id: UUID
    participant_id: UUID
    ts: datetime
    samples: int
    face_samples: int
    probabilities: tuple[float, ...] | None
    model_version: str


def aggregate(samples: list[Sample]) -> list[Bucket]:
    grouped: dict[tuple[UUID, UUID, datetime], list[Sample]] = {}
    for sample in samples:
        key = (sample.meeting_id, sample.participant_id, sample.ts.replace(microsecond=0))
        grouped.setdefault(key, []).append(sample)
    buckets = []
    for (meeting_id, participant_id, ts), points in grouped.items():
        faces = [point.probabilities for point in points if point.probabilities is not None]
        probabilities = tuple(sum(values) / len(faces) for values in zip(*faces, strict=True)) if faces else None
        buckets.append(
            Bucket(
                meeting_id,
                participant_id,
                ts,
                len(points),
                len(faces),
                probabilities,
                max(points, key=lambda sample: sample.ts).model_version,
            )
        )
    return buckets


@dataclass(frozen=True, slots=True)
class Point:
    ts: datetime
    p: tuple[float, ...] | None
    face_ratio: float
