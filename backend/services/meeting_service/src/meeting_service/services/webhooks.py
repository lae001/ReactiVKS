"""Вебхуки LiveKit (livekit-integration.md, «Вебхуки»): присутствие участников и закрытие пустой комнаты.

Каждый вебхук обрабатывается один раз: отметка в ``processed_webhooks`` и его эффект (отметки времени участника,
статус встречи, событие в outbox) фиксируются одной транзакцией. Повторная доставка видит отметку и ничего не делает.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import MeetingId
from meeting_service.domain.livekit import (
    LeaveReason,
    RoomEvent,
    RoomEventKind,
    WebhookVerifier,
    meeting_id_of_room,
    participant_id_of_identity,
)
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.outbox import EventOutbox
from meeting_service.repositories.participants import ParticipantRepository
from meeting_service.repositories.webhooks import ProcessedWebhooks
from meeting_service.services.event_payloads import meeting_ended, participant_joined, participant_left
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.logging import bind_context, get_logger

__all__ = ["HandleLiveKitWebhook"]

_logger = get_logger(__name__)


class HandleLiveKitWebhook:
    """Вебхук от LiveKit: проверить подпись и применить событие."""

    def __init__(self, *, session: AsyncSession, clock: Clock, verifier: WebhookVerifier) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._webhooks = ProcessedWebhooks(session)
        self._events = EventOutbox(session)
        self._clock = clock
        self._verifier = verifier

    async def execute(self, *, body: str, authorization: str) -> None:
        event = self._verifier.parse(body, authorization)
        meeting_id = meeting_id_of_room(event.room)
        if event.kind is RoomEventKind.OTHER or meeting_id is None:
            return
        bind_context(meeting_id=str(meeting_id))
        now = self._clock.now()
        async with transaction(self._session):
            if not await self._webhooks.remember(event.event_id, now=now):
                _logger.info("webhook already processed", kind=event.kind.value)
                return
            if event.kind is RoomEventKind.ROOM_FINISHED:
                await self._finish_meeting(meeting_id, event, now=now)
            else:
                await self._record_presence(meeting_id, event, now=now)

    async def _finish_meeting(self, meeting_id: MeetingId, event: RoomEvent, *, now: datetime) -> None:
        # Под блокировкой: «завершить» организатором и room_finished не должны завершить встречу дважды.
        meeting = await self._meetings.lock(meeting_id)
        if meeting is None:
            return
        at = event.occurred_at or now
        ended = meeting.room_closed(at)
        if ended is not meeting:
            await self._meetings.save_lifecycle(ended, now=now)
            await self._events.add(meeting_ended(ended), occurred_at=at)
            _logger.info("meeting ended", reason=ended.end_reason.value if ended.end_reason else None)

    async def _record_presence(self, meeting_id: MeetingId, event: RoomEvent, *, now: datetime) -> None:
        # ML-агент – не участник встречи: его вход и выход не отмечаются и не публикуются.
        participant_id = participant_id_of_identity(event.identity)
        if event.is_agent or participant_id is None:
            return
        participant = await self._participants.get(participant_id, meeting_id)
        if participant is None:
            _logger.warning("webhook for unknown participant", participant_id=str(participant_id))
            return
        at = event.occurred_at or now
        if event.kind is RoomEventKind.PARTICIPANT_JOINED:
            await self._participants.mark_joined(participant.id, at=at, now=now)
            await self._events.add(participant_joined(participant, joined_at=at), occurred_at=at)
        else:
            # Удаленный организатором выходит с причиной removed, даже если LiveKit назвал ее иначе.
            reason = LeaveReason.REMOVED if participant.is_removed else event.leave_reason
            await self._participants.mark_left(participant.id, at=at, now=now)
            await self._events.add(participant_left(participant, left_at=at, reason=reason), occurred_at=at)
