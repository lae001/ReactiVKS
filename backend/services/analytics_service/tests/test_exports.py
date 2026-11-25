"""Экспорт и отметки: права владельца, интервалы и сохранение при сборке."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.adapters.export import render_csv, render_pdf
from analytics_service.domain.report_jobs import ReportView
from analytics_service.models import PROBABILITIES, meetings, participants, series
from analytics_service.repositories.maintenance import purge_analytics
from analytics_service.services.exports import MeetingInProgress, ReportExports, ReportNotReady
from vks_common.clock import FixedClock
from vks_common.errors import NotFound, ValidationFailed

pytestmark = pytest.mark.integration


@pytest.fixture
async def data(sessions: async_sessionmaker[AsyncSession]) -> tuple[FixedClock, UUID, UUID, UUID]:
    now = datetime.now(UTC)
    owner, meeting, participant = uuid4(), uuid4(), uuid4()
    async with sessions() as session, session.begin():
        await session.execute(
            insert(meetings).values(
                meeting_id=meeting,
                owner_id=owner,
                title="Демо <test>",
                status="active",
                analysis_enabled=True,
                started_at=now - timedelta(seconds=60),
            )
        )
        await session.execute(
            insert(participants).values(
                participant_id=participant,
                meeting_id=meeting,
                display_name="=SUM(1)",
                role="guest",
                consent_state="granted",
            )
        )
    return FixedClock(now), owner, meeting, participant


async def test_marker_permissions_bounds_and_delete(
    sessions: async_sessionmaker[AsyncSession], data: tuple[FixedClock, UUID, UUID, UUID]
) -> None:
    clock, owner, meeting, participant = data
    async with sessions() as session:
        exports = ReportExports(session, clock)
        with pytest.raises(NotFound):
            await exports.mark(meeting, uuid4(), ts=None, label="Чужая", participant_id=None)
        with pytest.raises(ValidationFailed):
            await exports.mark(
                meeting, owner, ts=clock.now() + timedelta(seconds=1), label="Будущее", participant_id=None
            )
        with pytest.raises(ValidationFailed):
            await exports.mark(meeting, owner, ts=None, label="Чужой участник", participant_id=uuid4())
        mark = await exports.mark(meeting, owner, ts=None, label="Вопрос", participant_id=participant)
        assert mark.kind == "manual" and mark.created_by == owner
        with pytest.raises(NotFound):
            await exports.unmark(meeting, uuid4(), mark.id)
        await exports.unmark(meeting, owner, mark.id)
        with pytest.raises(NotFound):
            await exports.unmark(meeting, owner, mark.id)


async def test_export_state_csv_and_retention(
    sessions: async_sessionmaker[AsyncSession], data: tuple[FixedClock, UUID, UUID, UUID]
) -> None:
    clock, owner, meeting, participant = data
    async with sessions() as session:
        exports = ReportExports(session, clock)
        with pytest.raises(MeetingInProgress):
            await exports.csv_rows(meeting, owner)
        with pytest.raises(ReportNotReady):
            await exports.pdf_report(meeting, owner)
        async with session.begin():
            await session.execute(
                meetings.update().where(meetings.c.meeting_id == meeting).values(status="ended", ended_at=clock.now())
            )
            await session.execute(
                insert(series).values(
                    meeting_id=meeting,
                    participant_id=participant,
                    ts=clock.now() - timedelta(seconds=2),
                    samples=3,
                    face_samples=3,
                    model_version="test",
                    **dict.fromkeys(PROBABILITIES, 1 / 7),
                )
            )
        content = render_csv(await exports.csv_rows(meeting, owner))
        assert content.startswith(b"\xef\xbb\xbf")
        assert "'=SUM(1)" in content.decode("utf-8-sig")
        with pytest.raises(NotFound):
            await exports.csv_rows(meeting, uuid4())
        async with session.begin():
            await purge_analytics(session, clock.now() + timedelta(days=366), 365)
        assert await session.scalar(select(series.c.meeting_id).where(series.c.meeting_id == meeting)) is None


def test_pdf_has_signature_and_russian_text() -> None:
    now = datetime.now(UTC)
    report = ReportView(
        "Тест <script>",
        now,
        now,
        "ready",
        "test",
        {
            "overall": {"distribution": {}, "face_detected_ratio": 0, "negative_share": 0, "mean_probabilities": {}},
            "participants": [],
            "participant_count": 0,
            "consent_ratio": 0,
            "emotional_background": [],
        },
        [],
    )
    assert render_pdf(report).startswith(b"%PDF-")
