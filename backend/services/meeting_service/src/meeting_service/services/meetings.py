"""Встречи организатора: создание, история, карточка, завершение."""

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
    MeetingOverview,
    MeetingQuery,
    Organizer,
    check_analysis_fps,
    invite_code_from,
    normalize_title,
)
from meeting_service.repositories.meetings import InviteCodeTaken, MeetingPage, MeetingRepository
from meeting_service.repositories.organizer_settings import OrganizerSettingsRepository
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.errors import InternalError
from vks_common.ids import new_id
from vks_common.logging import bind_context, get_logger

__all__ = ["CreateMeeting", "EndMeeting", "GetMeeting", "ListMeetings"]

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


class EndMeeting:
    """Завершение встречи организатором. Повторный вызов отвечает тем же, ничего не меняя."""

    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
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
            overview = await self._meetings.overview(ended)

        if ended is not meeting:
            bind_context(meeting_id=str(meeting.id))
            _logger.info("meeting ended", reason=EndReason.ORGANIZER.value)
            await self._close_room(ended)
        return overview

    async def _close_room(self, meeting: Meeting) -> None:
        """Отключить участников – после фиксации: завершение в БД не откатывается из-за медиасервера.

        Если LiveKit недоступен, встреча все равно завершена: пустую комнату он закроет сам через
        ``empty_timeout``, а новые токены для нее уже не выдаются.
        """
        try:
            await self._livekit.delete_room(room_name(meeting))
        except LiveKitUnavailable:
            _logger.warning("room was not closed: livekit unavailable")
