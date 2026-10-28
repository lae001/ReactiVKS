"""Модерация встречи организатором (функция 6.3): участники, выключение микрофона и камеры, удаление.

Права проверяются в сценарии: чужая встреча – «не найдена». Вызовы LiveKit – после чтения и фиксации, вне транзакции.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.errors import MeetingNotFound, ParticipantNotFound
from meeting_service.domain.identifiers import MeetingId, ParticipantId, UserId
from meeting_service.domain.livekit import LiveKitGateway, MediaKind, room_name
from meeting_service.domain.meetings import Meeting
from meeting_service.domain.participants import Participant
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.participants import ParticipantRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.logging import bind_context, get_logger

__all__ = ["ListParticipants", "MuteParticipant", "RemoveParticipant"]

_logger = get_logger(__name__)


class ListParticipants:
    """Участники встречи с решением о согласии и присутствием в комнате – для панели организатора."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId) -> list[Participant]:
        async with transaction(self._session):
            meeting = await self._meetings.get_owned(meeting_id, owner_id)
            if meeting is None:
                raise MeetingNotFound()
            return await self._participants.list_for_meeting(meeting.id)


@dataclass(frozen=True, slots=True)
class _Target:
    meeting: Meeting
    participant: Participant


class MuteParticipant:
    """Выключить микрофон или камеру участника. Включает их обратно только сам участник."""

    def __init__(self, *, session: AsyncSession, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._livekit = livekit

    async def execute(
        self, *, owner_id: UserId, meeting_id: MeetingId, participant_id: ParticipantId, kind: MediaKind
    ) -> None:
        async with transaction(self._session):
            target = await _find_target(self._meetings, self._participants, owner_id, meeting_id, participant_id)
        target.meeting.ensure_in_progress()
        bind_context(meeting_id=str(meeting_id))
        await self._livekit.mute(room_name(target.meeting), target.participant.livekit_identity, kind)
        _logger.info("participant muted", participant_id=str(participant_id), kind=kind.value)


class RemoveParticipant:
    """Удалить участника из встречи: отключить от комнаты и закрыть повторный вход по его токену.

    Отметка ``is_removed`` фиксируется до вызова LiveKit: если он недоступен (``503``), повторный вход уже закрыт, а
    повтор запроса организатором доотключит участника.
    """

    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._clock = clock
        self._livekit = livekit

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId, participant_id: ParticipantId) -> None:
        async with transaction(self._session):
            target = await _find_target(self._meetings, self._participants, owner_id, meeting_id, participant_id)
            target.meeting.ensure_in_progress()
            removed = target.participant.removed()
            if removed is not target.participant:
                await self._participants.save_removed(removed.id, now=self._clock.now())
        bind_context(meeting_id=str(meeting_id))
        await self._livekit.remove(room_name(target.meeting), removed.livekit_identity)
        _logger.info("participant removed", participant_id=str(participant_id))


async def _find_target(
    meetings: MeetingRepository,
    participants: ParticipantRepository,
    owner_id: UserId,
    meeting_id: MeetingId,
    participant_id: ParticipantId,
) -> _Target:
    meeting = await meetings.get_owned(meeting_id, owner_id)
    if meeting is None:
        raise MeetingNotFound()
    participant = await participants.get(participant_id, meeting.id)
    if participant is None:
        raise ParticipantNotFound()
    return _Target(meeting=meeting, participant=participant)
