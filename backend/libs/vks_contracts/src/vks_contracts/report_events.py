"""Топик ``report.events`` – производитель analytics-service (через outbox), ключ – ``meeting_id``."""

from __future__ import annotations

from uuid import UUID

from vks_contracts.envelope import MeetingKeyed
from vks_contracts.topics import Topic

__all__ = ["ReportFailed", "ReportReady"]


class _ReportEvent(MeetingKeyed):
    topic = Topic.REPORT_EVENTS

    owner_id: UUID


class ReportReady(_ReportEvent):
    event_type = "report.ready"


class ReportFailed(_ReportEvent):
    event_type = "report.failed"

    reason: str
