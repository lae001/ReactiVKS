"""Чтение данных экспорта и изменение ручных отметок."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.models import PROBABILITIES, markers, meetings, participants, series


class ExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def meeting(self, meeting_id: UUID, owner_id: UUID) -> RowMapping | None:
        return (
            (
                await self.session.execute(
                    select(meetings)
                    .where(meetings.c.meeting_id == meeting_id, meetings.c.owner_id == owner_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )

    async def participant(self, meeting_id: UUID, participant_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(participants.c.participant_id).where(
                    participants.c.meeting_id == meeting_id, participants.c.participant_id == participant_id
                )
            )
            is not None
        )

    async def rows(self, meeting_id: UUID) -> list[RowMapping]:
        return list(
            (
                await self.session.execute(
                    select(
                        series.c.ts,
                        series.c.participant_id,
                        participants.c.display_name,
                        series.c.samples,
                        series.c.face_samples,
                        *(series.c[label] for label in PROBABILITIES),
                    )
                    .join(participants, participants.c.participant_id == series.c.participant_id)
                    .where(series.c.meeting_id == meeting_id)
                    .order_by(series.c.ts, series.c.participant_id)
                )
            ).mappings()
        )

    async def add_marker(
        self, meeting_id: UUID, owner_id: UUID, marker_id: UUID, ts: datetime, label: str, participant_id: UUID | None
    ) -> RowMapping:
        return (
            (
                await self.session.execute(
                    insert(markers)
                    .values(
                        id=marker_id,
                        meeting_id=meeting_id,
                        created_by=owner_id,
                        ts=ts,
                        kind="manual",
                        label=label,
                        participant_id=participant_id,
                    )
                    .returning(markers)
                )
            )
            .mappings()
            .one()
        )

    async def delete_marker(self, meeting_id: UUID, marker_id: UUID) -> bool:
        return (
            await self.session.scalar(
                delete(markers)
                .where(markers.c.meeting_id == meeting_id, markers.c.id == marker_id, markers.c.kind == "manual")
                .returning(markers.c.id)
            )
            is not None
        )
