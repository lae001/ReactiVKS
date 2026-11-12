"""Запись проекций из Kafka и удаление связанных рядов."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, false, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.models import consent_history, deleted_meetings, deleted_owners, meetings, participants, series


class Projections:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def put_meeting(
        self,
        meeting_id: UUID,
        owner_id: UUID,
        title: str,
        *,
        is_analyzed: bool,
        at: datetime,
        started_at: datetime | None,
    ) -> None:
        await self._lock_owner(owner_id)
        if await self.session.scalar(select(deleted_owners.c.owner_id).where(deleted_owners.c.owner_id == owner_id)):
            return
        if await self.session.scalar(
            select(deleted_meetings.c.meeting_id).where(deleted_meetings.c.meeting_id == meeting_id)
        ):
            return
        statement = insert(meetings).values(
            meeting_id=meeting_id,
            owner_id=owner_id,
            title=title,
            analysis_enabled=is_analyzed,
            status="active" if started_at is not None else "scheduled",
            started_at=started_at,
            updated_at=at,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[meetings.c.meeting_id],
                set_={
                    name: statement.excluded[name]
                    for name in ("title", "status", "analysis_enabled", "started_at", "updated_at")
                },
                where=(meetings.c.updated_at <= at) & (meetings.c.status == "scheduled")
                if started_at is not None
                else false(),
            )
        )

    async def update_meeting(self, meeting_id: UUID, at: datetime, **fields: object) -> None:
        await self.session.execute(
            update(meetings)
            .where(meetings.c.meeting_id == meeting_id, meetings.c.updated_at <= at)
            .values(updated_at=at, **fields)
        )

    async def register(
        self, meeting_id: UUID, participant_id: UUID, display_name: str, role: str, state: str, *, at: datetime
    ) -> None:
        if not await self._lock_meeting(meeting_id):
            return
        registered = await self.session.scalar(
            insert(participants)
            .values(
                meeting_id=meeting_id,
                participant_id=participant_id,
                display_name=display_name,
                role=role,
                consent_state=state,
                consent_decided_at=at,
                updated_at=at,
            )
            .on_conflict_do_nothing()
            .returning(participants.c.participant_id)
        )
        if registered is not None:
            await self._save_consent(participant_id, state, at=at)

    async def change_consent(self, meeting_id: UUID, participant_id: UUID, state: str, *, at: datetime) -> None:
        if not await self._lock_meeting(meeting_id):
            return
        changed = await self.session.scalar(
            update(participants)
            .where(
                participants.c.meeting_id == meeting_id,
                participants.c.participant_id == participant_id,
                (
                    (participants.c.consent_decided_at < at)
                    | ((participants.c.consent_decided_at == at) & (participants.c.consent_state != state))
                ),
            )
            .values(consent_state=state, consent_decided_at=at, updated_at=at)
            .returning(participants.c.participant_id)
        )
        if changed is None:
            return
        await self._save_consent(participant_id, state, at=at)
        if state != "granted":
            # При задержке топика согласий удаляем неоднозначную граничную корзину целиком.
            await self.session.execute(
                delete(series).where(
                    series.c.meeting_id == meeting_id,
                    series.c.participant_id == participant_id,
                    series.c.ts >= at.replace(microsecond=0),
                )
            )

    async def remove_meeting(self, meeting_id: UUID) -> None:
        await self._lock_meeting(meeting_id)
        await self.session.execute(insert(deleted_meetings).values(meeting_id=meeting_id).on_conflict_do_nothing())
        await self.session.execute(delete(series).where(series.c.meeting_id == meeting_id))
        await self.session.execute(delete(meetings).where(meetings.c.meeting_id == meeting_id))

    async def remove_owner(self, owner_id: UUID) -> None:
        await self._lock_owner(owner_id)
        await self.session.execute(insert(deleted_owners).values(owner_id=owner_id).on_conflict_do_nothing())
        ids = await self.session.scalars(
            select(meetings.c.meeting_id).where(meetings.c.owner_id == owner_id).order_by(meetings.c.meeting_id)
        )
        for meeting_id in ids:
            await self.remove_meeting(meeting_id)

    async def _lock_meeting(self, meeting_id: UUID) -> bool:
        value = await self.session.scalar(
            select(meetings.c.meeting_id).where(meetings.c.meeting_id == meeting_id).with_for_update()
        )
        return value is not None

    async def _lock_owner(self, owner_id: UUID) -> None:
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(owner_id), 0))))

    async def _save_consent(self, participant_id: UUID, state: str, *, at: datetime) -> None:
        await self.session.execute(
            insert(consent_history)
            .values(participant_id=participant_id, decided_at=at, is_granted=state == "granted")
            .on_conflict_do_update(
                index_elements=[consent_history.c.participant_id, consent_history.c.decided_at],
                set_={"is_granted": state == "granted"},
            )
        )
