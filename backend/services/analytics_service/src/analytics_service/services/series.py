"""Закрытие корзин и выдача временных рядов владельцу встречи."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.domain.series import BufferedSample, Point, Resolution, Sample, aggregate
from analytics_service.repositories.series import SeriesRepository
from vks_common.db import transaction
from vks_common.errors import NotFound

_CLOSE_DELAY = timedelta(seconds=3)
_PROJECTION_WAIT = timedelta(seconds=15)


@dataclass(frozen=True, slots=True)
class FlushResult:
    consumed: int
    next_offset: int


class FlushSamples:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def execute(
        self, partition: int, records: list[BufferedSample], *, now: datetime, force: bool = False
    ) -> FlushResult:
        async with self._sessions() as session, transaction(session):
            repository = SeriesRepository(session)
            offset = await repository.lock_offset(partition, records[0].offset)
            samples = [record.sample for record in records if record.offset >= offset and record.sample is not None]
            if samples:
                ids = {sample.meeting_id for sample in samples}
                meetings = await repository.lock_meetings(ids)
                deleted = await repository.deleted(ids - meetings.keys())
                consents = await repository.read_consents(
                    {sample.participant_id for sample in samples}, min(sample.ts for sample in samples)
                )
            else:
                meetings, deleted, consents = {}, set(), {}

            accepted: list[Sample] = []
            consumed = 0
            for record in records:
                sample = record.sample
                if record.offset >= offset and sample is not None and sample.meeting_id not in deleted:
                    meeting = meetings.get(sample.meeting_id)
                    participant = consents.get(sample.participant_id)
                    if meeting is None or participant is None:
                        if now - record.received_at < _PROJECTION_WAIT:
                            break
                    elif participant[0] == sample.meeting_id and meeting.analysis_enabled:
                        if not force and now < sample.ts.replace(microsecond=0) + _CLOSE_DELAY:
                            if now - record.received_at < _PROJECTION_WAIT:
                                break
                        elif (
                            meeting.started_at is not None
                            and sample.ts >= meeting.started_at
                            and (meeting.ended_at is None or sample.ts <= meeting.ended_at)
                            and _has_consent(participant[1], sample.ts)
                        ):
                            accepted.append(sample)
                consumed += 1

            if consumed:
                offset = max(offset, records[consumed - 1].offset + 1)
                await repository.write(aggregate(accepted))
                await repository.save_offset(partition, offset)
        return FlushResult(consumed, offset)


def _has_consent(history: list[tuple[datetime, bool]], ts: datetime) -> bool:
    return next((granted for at, granted in reversed(history) if at <= ts), False)


class ReadSeries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(
        self,
        meeting_id: UUID,
        owner_id: UUID,
        *,
        resolution: Resolution,
        participant_id: UUID | None,
        since: datetime | None,
    ) -> dict[UUID, list[Point]]:
        async with transaction(self._session):
            repository = SeriesRepository(self._session)
            if not await repository.owned(meeting_id, owner_id):
                raise NotFound()
            return await repository.read(meeting_id, resolution=resolution, participant_id=participant_id, since=since)
