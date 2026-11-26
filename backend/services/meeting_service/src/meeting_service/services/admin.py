"""Встречи администратора без доступа к аналитике участников."""

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import MeetingId
from meeting_service.domain.meetings import MeetingCursor, MeetingQuery
from meeting_service.repositories.meetings import MeetingPage, MeetingRepository
from vks_common.db import transaction


async def list_admin_meetings(
    session: AsyncSession, query: MeetingQuery, limit: int, after: MeetingCursor | None
) -> tuple[MeetingPage, dict[MeetingId, int]]:
    async with transaction(session):
        repository = MeetingRepository(session)
        page = await repository.list_owned(None, query, limit=limit, after=after)
        counts = await repository.online_counts([item.meeting.id for item in page.items])
        return page, counts
