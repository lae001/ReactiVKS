"""Реакция на события учетных записей из ``user.events`` (auth-service): блокировка и удаление организатора."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.errors import MeetingNotFound
from meeting_service.domain.identifiers import UserId
from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.repositories.blocked_users import BlockedUsers
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.services.meetings import DeleteMeeting
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.logging import get_logger

__all__ = ["DeleteOrganizerMeetings", "RecordUserBlock"]

_logger = get_logger(__name__)


class RecordUserBlock:
    """Проекция ``blocked_users``: заблокированный организатор не входит во встречи (``403 user_blocked``)."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._blocked = BlockedUsers(session)

    async def execute(self, *, user_id: UserId, is_blocked: bool, at: datetime) -> None:
        async with transaction(self._session):
            if is_blocked:
                await self._blocked.block(user_id, at=at)
            else:
                await self._blocked.unblock(user_id)
        _logger.info("user block recorded", user_id=str(user_id), is_blocked=is_blocked)


class DeleteOrganizerMeetings:
    """Учетная запись удалена – удалить все ее встречи тем же сценарием, что и ``DELETE /meetings/{id}``.

    Каждая встреча – своя транзакция (идущая еще и закрывает комнату LiveKit). Повторная доставка события находит
    только неудаленные встречи и доделывает то, что прервал сбой.
    """

    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._delete = DeleteMeeting(session=session, clock=clock, livekit=livekit)

    async def execute(self, *, owner_id: UserId) -> None:
        async with transaction(self._session):
            meeting_ids = await self._meetings.list_owned_ids(owner_id)
        for meeting_id in meeting_ids:
            try:
                await self._delete.execute(owner_id=owner_id, meeting_id=meeting_id)
            except MeetingNotFound:
                continue  # удалена между выборкой и удалением – цель достигнута
        _logger.info("organizer meetings deleted", user_id=str(owner_id), meetings=len(meeting_ids))
