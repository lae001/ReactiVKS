"""Хранение последнего желаемого состояния и аренда попытки доставки."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import ParticipantId
from meeting_service.domain.livekit import RoomAccess
from meeting_service.domain.participants import Participant
from meeting_service.models import LiveKitSyncRow


@dataclass(frozen=True, slots=True)
class LiveKitSyncJob:
    id: int
    revision: int
    attempts: int
    locked_until: datetime
    room: str
    identity: str
    attributes: dict[str, str]


class LiveKitSyncQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, participant: Participant, access: RoomAccess, *, now: datetime) -> None:
        statement = insert(LiveKitSyncRow).values(
            meeting_id=participant.meeting_id,
            participant_id=participant.id,
            attributes={"vks.consent": access.attributes["vks.consent"]},
            next_attempt_at=now,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[LiveKitSyncRow.participant_id],
                set_={
                    "attributes": statement.excluded.attributes,
                    "revision": LiveKitSyncRow.revision + 1,
                    "attempts": 0,
                    "next_attempt_at": now,
                },
            )
        )

    async def claim(
        self, *, now: datetime, locked_until: datetime, participant_id: ParticipantId | None
    ) -> LiveKitSyncJob | None:
        statement = (
            select(LiveKitSyncRow)
            .where(
                LiveKitSyncRow.next_attempt_at <= now,
                or_(LiveKitSyncRow.locked_until.is_(None), LiveKitSyncRow.locked_until <= now),
            )
            .order_by(LiveKitSyncRow.next_attempt_at, LiveKitSyncRow.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if participant_id is not None:
            statement = statement.where(LiveKitSyncRow.participant_id == participant_id)
        row = await self._session.scalar(statement)
        if row is None:
            return None
        row.locked_until = locked_until
        return LiveKitSyncJob(
            row.id,
            row.revision,
            row.attempts,
            locked_until,
            str(row.meeting_id),
            f"p_{row.participant_id}",
            row.attributes,
        )

    async def finish(self, job: LiveKitSyncJob, *, retry_at: datetime | None) -> bool:
        lease = (LiveKitSyncRow.id == job.id, LiveKitSyncRow.locked_until == job.locked_until)
        current = (*lease, LiveKitSyncRow.revision == job.revision)
        if retry_at is None:
            removed = await self._session.scalar(delete(LiveKitSyncRow).where(*current).returning(LiveKitSyncRow.id))
            if removed is not None:
                return True
        else:
            await self._session.execute(
                update(LiveKitSyncRow).where(*current).values(next_attempt_at=retry_at, attempts=job.attempts + 1)
            )
        # Новое решение могло прийти, пока выполнялся RPC. Оно уже в очереди и сохраняет свое время доставки.
        await self._session.execute(update(LiveKitSyncRow).where(*lease).values(locked_until=None))
        return False
