"""Сводка, скользящая валентность и ключевые моменты."""

from bisect import bisect_right
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from analytics_service.domain.series import PROBABILITY_COUNT, Bucket

_NEGATIVE = (0, 1, 2, 4)


@dataclass(frozen=True, slots=True)
class ReportParticipant:
    id: UUID
    display_name: str
    consent: str


@dataclass(frozen=True, slots=True)
class Marker:
    ts: datetime
    participant_id: UUID | None
    label: str
    details: dict[str, float]


@dataclass(frozen=True, slots=True)
class ReportContent:
    summary: dict[str, object]
    markers: list[Marker]
    model_version: str | None


def build_report(
    participants: list[ReportParticipant], buckets: list[Bucket], labels: tuple[str, ...], shift_threshold: float
) -> ReportContent:
    by_participant: dict[UUID, list[Bucket]] = {}
    by_second: dict[datetime, list[tuple[float, ...]]] = {}
    for bucket in buckets:
        by_participant.setdefault(bucket.participant_id, []).append(bucket)
        if bucket.probabilities is not None:
            by_second.setdefault(bucket.ts, []).append(bucket.probabilities)

    distributions: list[tuple[float, ...]] = []
    probabilities: list[tuple[float, ...]] = []
    face_ratios: list[float] = []
    participant_summaries = []
    markers = []
    for participant in participants:
        rows = by_participant.get(participant.id, [])
        points = [(row.ts, row.probabilities) for row in rows if row.probabilities is not None]
        ratio = sum(row.face_samples / row.samples for row in rows) / len(rows) if rows else None
        if ratio is not None:
            face_ratios.append(ratio)
        distribution = dominant = mean = None
        if points:
            counts = Counter(_dominant(values) for _, values in points)
            distribution = tuple(counts[i] / len(points) for i in range(PROBABILITY_COUNT))
            mean = _average([values for _, values in points])
            dominant = labels[_dominant(distribution)]
            distributions.append(distribution)
            probabilities.append(mean)
            shifts, _ = _timeline(points, participant.id, shift_threshold)
            markers.extend(shifts)
        participant_summaries.append(
            {
                "participant_id": str(participant.id),
                "display_name": participant.display_name,
                "consent": participant.consent,
                "distribution": _labeled(labels, distribution),
                "mean_probabilities": _labeled(labels, mean),
                "dominant": dominant,
                "face_detected_ratio": ratio,
                "analyzed_seconds": len(rows),
            }
        )

    overall_points = [(ts, _average(values)) for ts, values in sorted(by_second.items())]
    shifts, background = _timeline(overall_points, None, shift_threshold)
    markers.extend(shifts)
    overall_distribution = _average(distributions)
    summary = {
        "overall": {
            "distribution": _labeled(labels, overall_distribution),
            "face_detected_ratio": sum(face_ratios) / len(face_ratios) if face_ratios else 0.0,
            "negative_share": sum(overall_distribution[index] for index in _NEGATIVE),
            "mean_probabilities": _labeled(labels, _average(probabilities)),
        },
        "participants": participant_summaries,
        "participant_count": len(participants),
        "consent_ratio": sum(item.consent == "granted" for item in participants) / len(participants)
        if participants
        else 0,
        "emotional_background": background,
    }
    latest = max(buckets, key=lambda row: row.ts, default=None)
    return ReportContent(summary, markers, latest.model_version if latest is not None else None)


def _dominant(probabilities: tuple[float, ...]) -> int:
    return max(range(len(probabilities)), key=probabilities.__getitem__)


def _average(values: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    if not values:
        return (0.0,) * PROBABILITY_COUNT
    return tuple(sum(items) / len(values) for items in zip(*values, strict=True))


def _labeled(labels: tuple[str, ...], values: tuple[float, ...] | None) -> dict[str, float] | None:
    return dict(zip(labels, values, strict=True)) if values is not None else None


def _timeline(
    points: list[tuple[datetime, tuple[float, ...]]], participant_id: UUID | None, threshold: float
) -> tuple[list[Marker], list[dict[str, str | float]]]:
    times = [ts for ts, _ in points]
    negative = [0.0]
    valence = [0.0]
    markers: list[Marker] = []
    background: list[dict[str, str | float]] = []
    last_candidate_at: datetime | None = None
    for i, (ts, p) in enumerate(points, 1):
        neg = sum(p[index] for index in _NEGATIVE)
        negative.append(negative[-1] + neg)
        valence.append(valence[-1] + p[3] + 0.5 * p[5] - neg)
        recent = bisect_right(times, ts - timedelta(seconds=10), hi=i)
        previous = bisect_right(times, ts - timedelta(seconds=40), hi=recent)
        value = (valence[i] - valence[recent]) / (i - recent)
        if participant_id is None:
            background.append({"ts": ts.isoformat(), "valence": value})
        if previous == recent:
            continue
        negative_delta = (negative[i] - negative[recent]) / (i - recent) - (negative[recent] - negative[previous]) / (
            recent - previous
        )
        valence_delta = value - (valence[recent] - valence[previous]) / (recent - previous)
        magnitude = max(abs(negative_delta), abs(valence_delta))
        if magnitude <= threshold:
            continue
        marker = Marker(
            ts,
            participant_id,
            "Изменение эмоционального фона",
            {"negative_delta": negative_delta, "valence_delta": valence_delta, "magnitude": magnitude},
        )
        if last_candidate_at is not None and ts - last_candidate_at < timedelta(seconds=30):
            if magnitude > markers[-1].details["magnitude"]:
                markers[-1] = marker
        else:
            markers.append(marker)
        last_candidate_at = ts
    return markers, background
