"""Вход во встречу: организатора (по access-токену), гостя (по коду приглашения) и повторный вход гостя.

Порядок везде один: прочитать и проверить → подготовить комнату LiveKit (сеть – вне транзакции) → в короткой
транзакции перепроверить и записать участника и согласие → подписать токен LiveKit (локально, без сети). Если
LiveKit недоступен, в БД ничего не меняется и клиент получает ``503 livekit_unavailable``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import (
    CURRENT_NOTICE,
    ConsentDecision,
    ConsentNotice,
    ConsentRecord,
    check_notice_version,
    decide_consent,
)
from meeting_service.domain.errors import MeetingNotFound, ParticipantRemoved, ParticipantTokenInvalid
from meeting_service.domain.identifiers import MeetingId, ParticipantId
from meeting_service.domain.livekit import LiveKitGateway, room_access, room_name
from meeting_service.domain.meetings import Meeting, Organizer, is_invite_code
from meeting_service.domain.participants import (
    MAX_DISPLAY_NAME_LENGTH,
    PARTICIPANT_TOKEN_PREFIX,
    ConsentState,
    Participant,
    ParticipantRole,
    hash_participant_token,
    normalize_display_name,
)
from meeting_service.repositories.consents import ConsentLog
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.outbox import EventOutbox
from meeting_service.repositories.participants import ParticipantRepository
from meeting_service.services.event_payloads import (
    consent_changed,
    meeting_started,
    participant_registered,
)
from vks_common.clock import Clock
from vks_common.db import transaction
from vks_common.ids import new_id, new_token
from vks_common.logging import bind_context, get_logger

__all__ = [
    "GetJoinInfo",
    "GuestJoinResult",
    "JoinAsGuest",
    "JoinAsOrganizer",
    "JoinInfo",
    "JoinResult",
    "RejoinAsGuest",
    "RequestOrigin",
]

_logger = get_logger(__name__)

# User-Agent попадает в журнал согласий как справка; длиннее этого обрезается.
_MAX_USER_AGENT_LENGTH = 512


@dataclass(frozen=True, slots=True)
class RequestOrigin:
    """Откуда пришло решение о согласии – пишется в журнал согласий."""

    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class JoinResult:
    """С чем участник подключается к комнате."""

    meeting: Meeting
    participant: Participant
    livekit_url: str
    livekit_token: str


@dataclass(frozen=True, slots=True)
class GuestJoinResult:
    """Вход гостя. ``participant_token`` в открытом виде существует только здесь и в ответе клиенту."""

    join: JoinResult
    participant_token: str


@dataclass(frozen=True, slots=True)
class JoinInfo:
    """Что показывает лобби гостя до входа."""

    meeting: Meeting
    consent_notice: ConsentNotice | None


class _ConsentJournal:
    """Запись решения в журнал – общая часть входа организатора и гостя."""

    def __init__(self, session: AsyncSession, notice: ConsentNotice) -> None:
        self._log = ConsentLog(session)
        self._notice = notice

    async def record(
        self,
        meeting: Meeting,
        participant: Participant,
        origin: RequestOrigin,
        *,
        decided_at: datetime,
    ) -> None:
        """Журналируется только решение: во встрече без анализа решать нечего."""
        if participant.consent_state is ConsentState.NOT_REQUIRED:
            return
        await self._log.append(
            ConsentRecord(
                meeting_id=meeting.id,
                participant_id=participant.id,
                display_name=participant.display_name,
                meeting_title=meeting.title,
                decision=participant.consent_state,
                notice_version=self._notice.version,
                decided_at=decided_at,
                ip=origin.ip,
                user_agent=origin.user_agent[:_MAX_USER_AGENT_LENGTH] if origin.user_agent else None,
            )
        )


class JoinAsOrganizer:
    """Вход организатора в свою встречу: первый вход активирует ее и создает комнату LiveKit."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        clock: Clock,
        livekit: LiveKitGateway,
        notice: ConsentNotice = CURRENT_NOTICE,
    ) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._journal = _ConsentJournal(session, notice)
        self._events = EventOutbox(session)
        self._notice = notice
        self._clock = clock
        self._livekit = livekit

    async def execute(
        self,
        *,
        organizer: Organizer,
        meeting_id: MeetingId,
        consent: ConsentDecision | None,
        origin: RequestOrigin,
    ) -> JoinResult:
        bind_context(meeting_id=str(meeting_id))
        async with transaction(self._session):
            meeting = await self._meetings.get_owned(meeting_id, organizer.user_id)
        if meeting is None:
            raise MeetingNotFound()
        meeting.started(self._clock.now())
        consent_state = decide_consent(analysis_enabled=meeting.analysis_enabled, decision=consent)

        await self._livekit.ensure_room(room_name(meeting))

        now = self._clock.now()
        async with transaction(self._session):
            locked = await self._meetings.lock_owned(meeting_id, organizer.user_id)
            if locked is None:
                raise MeetingNotFound()
            # Перепроверка под блокировкой: пока создавалась комната, встречу могли завершить.
            started = locked.started(now)
            if started is not locked:
                await self._meetings.save_lifecycle(started, now=now)
                await self._events.add(meeting_started(started), occurred_at=now)
                _logger.info("meeting started")
            participant = await self._participants.get_organizer(started.id, organizer.user_id)
            if participant is None:
                participant = self._new_participant(started, organizer, consent_state, now=now)
                await self._participants.add(participant)
                await self._journal.record(started, participant, origin, decided_at=now)
                await self._events.add(participant_registered(participant), occurred_at=now)
            elif participant.consent_state is not consent_state:
                # Организатор вошел снова и решил иначе – новое решение тоже в журнал и в событие.
                participant = participant.with_consent(consent_state)
                await self._participants.save_consent(participant.id, consent_state, now=now)
                await self._journal.record(started, participant, origin, decided_at=now)
                await self._events.add(
                    consent_changed(participant, notice_version=self._notice.version, decided_at=now),
                    occurred_at=now,
                )

        return JoinResult(
            meeting=started,
            participant=participant,
            livekit_url=self._livekit.public_url,
            livekit_token=self._livekit.issue_token(room_access(started, participant)),
        )

    @staticmethod
    def _new_participant(
        meeting: Meeting,
        organizer: Organizer,
        consent_state: ConsentState,
        *,
        now: datetime,
    ) -> Participant:
        return Participant(
            id=ParticipantId(new_id()),
            meeting_id=meeting.id,
            user_id=organizer.user_id,
            # Имя учетной записи – до 100 символов, имя участника – до 64.
            display_name=organizer.name.strip()[:MAX_DISPLAY_NAME_LENGTH],
            role=ParticipantRole.ORGANIZER,
            consent_state=consent_state,
            created_at=now,
        )


class GetJoinInfo:
    """Публичная информация о встрече для лобби гостя (без аутентификации)."""

    def __init__(self, *, session: AsyncSession, notice: ConsentNotice = CURRENT_NOTICE) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._notice = notice

    async def execute(self, *, invite_code: str) -> JoinInfo:
        meeting = await _find_by_invite_code(self._session, self._meetings, invite_code)
        return JoinInfo(meeting=meeting, consent_notice=self._notice if meeting.analysis_enabled else None)


class JoinAsGuest:
    """Вход гостя по коду приглашения: участник, решение о согласии, токен участника и токен LiveKit."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        clock: Clock,
        livekit: LiveKitGateway,
        notice: ConsentNotice = CURRENT_NOTICE,
        token_factory: Callable[[], str] = new_token,
    ) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._journal = _ConsentJournal(session, notice)
        self._events = EventOutbox(session)
        self._notice = notice
        self._clock = clock
        self._livekit = livekit
        self._token_factory = token_factory

    async def execute(
        self,
        *,
        invite_code: str,
        display_name: str,
        consent: ConsentDecision | None,
        notice_version: str | None,
        origin: RequestOrigin,
    ) -> GuestJoinResult:
        name = normalize_display_name(display_name)
        meeting = await _find_by_invite_code(self._session, self._meetings, invite_code)
        bind_context(meeting_id=str(meeting.id))
        meeting.ensure_open_for_guests()
        consent_state = decide_consent(analysis_enabled=meeting.analysis_enabled, decision=consent)
        if meeting.analysis_enabled:
            check_notice_version(notice_version, notice=self._notice)

        # Комнату создал вход организатора, но LiveKit мог закрыть ее, пока в ней никого не было.
        await self._livekit.ensure_room(room_name(meeting))

        participant_token = PARTICIPANT_TOKEN_PREFIX + self._token_factory()
        participant = Participant(
            id=ParticipantId(new_id()),
            meeting_id=meeting.id,
            display_name=name,
            role=ParticipantRole.GUEST,
            consent_state=consent_state,
            created_at=self._clock.now(),
        )
        async with transaction(self._session):
            current = await self._meetings.get(meeting.id)
            if current is None:
                raise MeetingNotFound()
            current.ensure_open_for_guests()
            await self._participants.add(participant, token_hash=hash_participant_token(participant_token))
            await self._journal.record(current, participant, origin, decided_at=participant.created_at)
            await self._events.add(participant_registered(participant), occurred_at=participant.created_at)

        # В журнал – идентификаторы, не имя гостя и не токен.
        _logger.info("guest joined", participant_id=str(participant.id), consent=consent_state.value)
        join = JoinResult(
            meeting=current,
            participant=participant,
            livekit_url=self._livekit.public_url,
            livekit_token=self._livekit.issue_token(room_access(current, participant)),
        )
        return GuestJoinResult(join=join, participant_token=participant_token)


class RejoinAsGuest:
    """Новый токен LiveKit гостю после перезагрузки вкладки – по его токену участника."""

    def __init__(self, *, session: AsyncSession, livekit: LiveKitGateway) -> None:
        self._session = session
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._livekit = livekit

    async def execute(self, *, participant_token: str) -> JoinResult:
        async with transaction(self._session):
            participant = await self._participants.get_by_token_hash(hash_participant_token(participant_token))
            meeting = await self._meetings.get(participant.meeting_id) if participant is not None else None
        if participant is None or meeting is None:
            raise ParticipantTokenInvalid()
        bind_context(meeting_id=str(meeting.id))
        if participant.is_removed:
            raise ParticipantRemoved()
        meeting.ensure_open_for_guests()

        await self._livekit.ensure_room(room_name(meeting))
        return JoinResult(
            meeting=meeting,
            participant=participant,
            livekit_url=self._livekit.public_url,
            livekit_token=self._livekit.issue_token(room_access(meeting, participant)),
        )


async def _find_by_invite_code(session: AsyncSession, meetings: MeetingRepository, invite_code: str) -> Meeting:
    """Встреча по коду приглашения. Строка не того формата – «не найдена» без запроса к БД."""
    if not is_invite_code(invite_code):
        raise MeetingNotFound()
    async with transaction(session):
        meeting = await meetings.get_by_invite_code(invite_code)
    if meeting is None:
        raise MeetingNotFound()
    return meeting
