"""Чтение встречи для внутренних потребителей."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.errors import MeetingNotFound
from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.domain.meetings import Meeting, MeetingOverview
from meeting_service.domain.participants import Participant
from meeting_service.repositories.blocked_users import BlockedUsers
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.participants import ParticipantRepository
from vks_common.db import transaction


@dataclass(frozen=True, slots=True)
class MeetingSnapshot:
    overview: MeetingOverview
    participants: list[Participant]


class ReadMeetingSnapshot:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)

    async def execute(self, meeting_id: MeetingId) -> MeetingSnapshot:
        async with transaction(self._session):
            meeting = await self._meetings.get(meeting_id)
            if meeting is None:
                raise MeetingNotFound()
            overview = await self._meetings.overview(meeting)
            participants = await self._participants.list_for_meeting(meeting_id)
        return MeetingSnapshot(overview, participants)


class CheckMeetingAccess:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._blocked = BlockedUsers(session)

    async def execute(self, meeting_id: MeetingId, user_id: UserId) -> Meeting | None:
        async with transaction(self._session):
            if await self._blocked.is_blocked(user_id):
                return None
            return await self._meetings.get_owned(meeting_id, user_id)
