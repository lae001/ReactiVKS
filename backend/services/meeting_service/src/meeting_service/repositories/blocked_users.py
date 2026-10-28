"""Проекция блокировок организаторов из ``user.events``: ``meeting.blocked_users``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import UserId
from meeting_service.models import BlockedUserRow

__all__ = ["BlockedUsers"]


class BlockedUsers:
    """Идемпотентна: повторная блокировка и повторная разблокировка ничего не меняют.

    Порядок событий одного пользователя сохраняет Kafka (ключ – ``user_id``), поэтому последнее событие и определяет
    состояние, в том числе при повторном чтении после сбоя.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def block(self, user_id: UserId, *, at: datetime) -> None:
        statement = insert(BlockedUserRow).values(user_id=user_id, blocked_at=at)
        await self._session.execute(statement.on_conflict_do_nothing(index_elements=[BlockedUserRow.user_id]))

    async def unblock(self, user_id: UserId) -> None:
        await self._session.execute(delete(BlockedUserRow).where(BlockedUserRow.user_id == user_id))

    async def is_blocked(self, user_id: UserId) -> bool:
        statement = select(BlockedUserRow.user_id).where(BlockedUserRow.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none() is not None
