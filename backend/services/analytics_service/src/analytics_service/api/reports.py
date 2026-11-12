"""Ряды эмоций для владельца встречи."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.domain.series import Resolution
from analytics_service.schemas.series import ParticipantSeries, SeriesPoint, SeriesResponse
from analytics_service.services.series import ReadSeries
from vks_common.auth import CurrentUser
from vks_common.db import get_session
from vks_contracts.ml_events import EMOTIONS

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{meeting_id}/series")
async def read_series(
    meeting_id: UUID,
    user: CurrentUser,
    session: Session,
    resolution: Resolution = "5s",
    participant_id: UUID | None = None,
    since: AwareDatetime | None = None,
) -> SeriesResponse:
    rows = await ReadSeries(session).execute(
        meeting_id, user.user_id, resolution=resolution, participant_id=participant_id, since=since
    )
    return SeriesResponse(
        resolution=resolution,
        labels=EMOTIONS,
        series=[
            ParticipantSeries(
                participant_id=identity,
                points=[SeriesPoint(ts=point.ts, p=point.p, face_ratio=point.face_ratio) for point in points],
            )
            for identity, points in rows.items()
        ],
    )
