"""Обработчик ``user.events`` (группа ``meeting``): блокировка и удаление организатора.

Идемпотентен (conventions.md, §7): проекция блокировок – ``ON CONFLICT`` и ``DELETE``, удаление встреч находит только
неудаленные. Недоступная БД – временный сбой: потребитель повторит сообщение, не продвигая смещение.
"""

from __future__ import annotations

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meeting_service.domain.identifiers import UserId
from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.services.user_events import DeleteOrganizerMeetings, RecordUserBlock
from vks_common.clock import Clock
from vks_common.kafka.consumer import TemporaryFailure
from vks_contracts import ParsedEvent
from vks_contracts.user_events import UserBlocked, UserDeleted, UserUnblocked

__all__ = ["UserEventsHandler"]


class UserEventsHandler:
    """``EventHandler`` потребителя: сессия на сообщение, сценарий по типу события."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        livekit: LiveKitGateway,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock
        self._livekit = livekit

    async def __call__(self, event: ParsedEvent) -> None:
        payload = event.payload
        try:
            async with self._sessions() as session:
                if isinstance(payload, UserBlocked | UserUnblocked):
                    await RecordUserBlock(session=session).execute(
                        user_id=UserId(payload.user_id),
                        is_blocked=isinstance(payload, UserBlocked),
                        at=event.envelope.occurred_at,
                    )
                elif isinstance(payload, UserDeleted):
                    await DeleteOrganizerMeetings(session=session, clock=self._clock, livekit=self._livekit).execute(
                        owner_id=UserId(payload.user_id)
                    )
        except (OperationalError, InterfaceError, OSError) as error:
            raise TemporaryFailure(type(error).__name__) from error
