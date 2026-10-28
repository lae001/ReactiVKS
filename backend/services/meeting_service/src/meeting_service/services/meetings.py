"""Встречи организатора: создание, история, карточка, изменение, завершение, удаление."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.errors import LiveKitUnavailable, MeetingNotFound
from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.domain.livekit import LiveKitGateway, room_name
from meeting_service.domain.meetings import (
    INVITE_CODE_ENTROPY_BYTES,
    EndReason,
    Meeting,
    MeetingCursor,
    MeetingEdit,
    MeetingOverview,
    MeetingQuery,
    MeetingStatus,
    Organizer,
    check_analysis_fps,
    invite_code_from,
    normalize_title,
)
from meeting_service.repositories.meetings import InviteCodeTaken, MeetingPage, MeetingRepository
from meeting_service.repositories.organizer_settings import OrganizerSettingsRepository
from meeting_service.repositories.outbox import EventOutbox
from meeting_service.services.event_payloads import (
    meeting_closed,
    meeting_created,
    meeting_deleted,
    meeting_ended,
    meeting_updated,
)
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.errors import InternalError
from vks_common.ids import new_id
from vks_common.logging import bind_context, get_logger

__all__ = ["CreateMeeting", "DeleteMeeting", "EndMeeting", "GetMeeting", "ListMeetings", "UpdateMeeting"]

_logger = get_logger(__name__)

# Совпадение 50-битных случайных кодов – событие на грани невозможного; несколько попыток покрывают его с запасом,
# а бесконечный цикл скрыл бы сломанный источник случайности.
_INVITE_CODE_ATTEMPTS = 5


class CreateMeeting:
    """Новая встреча организатора (UC-2). Не указанные параметры анализа – из настроек организатора."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        clock: Clock,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._settings = OrganizerSettingsRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock
        self._random_bytes = random_bytes

    async def execute(
        self,
        *,
        organizer: Organizer,
        title: str,
        scheduled_at: datetime | None = None,
        analysis_enabled: bool | None = None,
        analysis_fps: int | None = None,
    ) -> MeetingOverview:
        normalized_title = normalize_title(title)
        if analysis_fps is not None:
            check_analysis_fps(analysis_fps)
        async with transaction(self._session):
            defaults = await self._settings.get_defaults(organizer.user_id)

        for _ in range(_INVITE_CODE_ATTEMPTS):
            meeting = Meeting.schedule(
                meeting_id=MeetingId(new_id()),
                organizer=organizer,
                title=normalized_title,
                invite_code=invite_code_from(self._random_bytes(INVITE_CODE_ENTROPY_BYTES)),
                scheduled_at=scheduled_at,
                analysis_enabled=defaults.enabled if analysis_enabled is None else analysis_enabled,
                analysis_fps=defaults.fps if analysis_fps is None else analysis_fps,
                now=self._clock.now(),
            )
            # Совпавший код обнаруживает ограничение БД: проверка заранее не защитила бы от одновременной вставки.
            try:
                async with transaction(self._session):
                    await self._meetings.add(meeting)
                    await self._events.add(meeting_created(meeting), occurred_at=meeting.created_at)
            except InviteCodeTaken:
                _logger.warning("invite code collision, retrying")
                continue
            bind_context(meeting_id=str(meeting.id))
            _logger.info("meeting created", analysis_enabled=meeting.analysis_enabled)
            return MeetingOverview(meeting=meeting, participants_count=0)
        raise InternalError("Could not generate a unique invite code")


class ListMeetings:
    """История и запланированные встречи организатора, новые сверху."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)

    async def execute(
        self,
        *,
        owner_id: UserId,
        query: MeetingQuery,
        limit: int,
        after: MeetingCursor | None = None,
    ) -> MeetingPage:
        async with transaction(self._session):
            return await self._meetings.list_owned(owner_id, query, limit=limit, after=after)


class GetMeeting:
    """Карточка встречи. Чужая встреча – «не найдена», а не «запрещена»: ответ не раскрывает, что она есть."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId) -> MeetingOverview:
        async with transaction(self._session):
            meeting = await self._meetings.get_owned(meeting_id, owner_id)
            if meeting is None:
                raise MeetingNotFound()
            return await self._meetings.overview(meeting)


class UpdateMeeting:
    """Изменение встречи организатором (``PATCH``). Без изменений – ни записи, ни события."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId, edit: MeetingEdit) -> MeetingOverview:
        now = self._clock.now()
        async with transaction(self._session):
            # Под блокировкой: одновременный первый вход организатора не должен пропустить смену параметров анализа.
            meeting = await self._meetings.lock_owned(meeting_id, owner_id)
            if meeting is None:
                raise MeetingNotFound()
            edited = meeting.edited(edit)
            if edited is not meeting:
                await self._meetings.save_details(edited, now=now)
                await self._events.add(meeting_updated(edited), occurred_at=now)
            return await self._meetings.overview(edited)


class EndMeeting:
    """Завершение встречи организатором. Повторный вызов отвечает тем же, ничего не меняя."""

    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock
        self._livekit = livekit

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId) -> MeetingOverview:
        now = self._clock.now()
        async with transaction(self._session):
            meeting = await self._meetings.lock_owned(meeting_id, owner_id)
            if meeting is None:
                raise MeetingNotFound()
            ended = meeting.ended(now, EndReason.ORGANIZER)
            if ended is not meeting:
                await self._meetings.save_lifecycle(ended, now=now)
                await self._events.add(meeting_ended(ended), occurred_at=now)
            overview = await self._meetings.overview(ended)

        if ended is not meeting:
            bind_context(meeting_id=str(meeting.id))
            _logger.info("meeting ended", reason=EndReason.ORGANIZER.value)
            await _close_room(self._livekit, ended)
        return overview


class DeleteMeeting:
    """Удаление встречи организатором: идущая сначала завершается, незапущенная – отменяется.

    Удаление мягкое; аналитику встречи потребители удаляют по событию ``meeting.deleted``. Повторное удаление –
    «не найдена»: удаленной встречи для организатора больше нет.
    """

    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._events = EventOutbox(session)
        self._clock = clock
        self._livekit = livekit

    async def execute(self, *, owner_id: UserId, meeting_id: MeetingId) -> None:
        now = self._clock.now()
        async with transaction(self._session):
            meeting = await self._meetings.lock_owned(meeting_id, owner_id)
            if meeting is None:
                raise MeetingNotFound()
            closed = meeting.closed(now)
            if closed is not meeting:
                await self._meetings.save_lifecycle(closed, now=now)
                await self._events.add(meeting_closed(closed), occurred_at=now)
            await self._meetings.soft_delete(meeting.id, now=now)
            await self._events.add(meeting_deleted(closed), occurred_at=now)

        bind_context(meeting_id=str(meeting.id))
        _logger.info("meeting deleted", status=meeting.status.value)
        if meeting.status is MeetingStatus.ACTIVE:
            await _close_room(self._livekit, closed)


async def _close_room(livekit: LiveKitGateway, meeting: Meeting) -> None:
    """Отключить участников – после фиксации: завершение в БД не откатывается из-за медиасервера.

    Если LiveKit недоступен, встреча все равно завершена: пустую комнату он закроет сам через ``empty_timeout``,
    а новые токены для нее уже не выдаются.
    """
    try:
        await livekit.delete_room(room_name(meeting))
    except LiveKitUnavailable:
        _logger.warning("room was not closed: livekit unavailable")
