"""Изменение согласия участника во время встречи."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.consent import CURRENT_NOTICE, ConsentChange, check_notice_version
from meeting_service.domain.errors import (
    AnalysisDisabled,
    MeetingNotFound,
    ParticipantNotFound,
    ParticipantRemoved,
    ParticipantTokenInvalid,
)
from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.domain.livekit import LiveKitGateway, room_access
from meeting_service.domain.meetings import Meeting
from meeting_service.domain.participants import ConsentState, Participant, hash_participant_token
from meeting_service.repositories.livekit_sync import LiveKitSyncQueue
from meeting_service.repositories.meetings import MeetingRepository
from meeting_service.repositories.outbox import EventOutbox
from meeting_service.repositories.participants import ParticipantRepository
from meeting_service.services.event_payloads import consent_changed
from meeting_service.services.joining import ConsentJournal, RequestOrigin
from meeting_service.services.livekit_sync import SyncLiveKitConsent
from vks_common.clock import Clock
from vks_common.db import transaction


@dataclass(frozen=True, slots=True)
class OrganizerConsent:
    user_id: UserId
    meeting_id: MeetingId


@dataclass(frozen=True, slots=True)
class ConsentResult:
    state: ConsentState
    synced: bool


class ChangeConsent:
    def __init__(self, *, session: AsyncSession, clock: Clock, livekit: LiveKitGateway) -> None:
        self._session = session
        self._clock = clock
        self._meetings = MeetingRepository(session)
        self._participants = ParticipantRepository(session)
        self._journal = ConsentJournal(session, CURRENT_NOTICE)
        self._events = EventOutbox(session)
        self._queue = LiveKitSyncQueue(session)
        self._sync = SyncLiveKitConsent(session=session, clock=clock, livekit=livekit)

    async def execute(
        self,
        *,
        caller: OrganizerConsent | str,
        decision: ConsentChange,
        notice_version: str | None,
        origin: RequestOrigin,
    ) -> ConsentResult:
        state = ConsentState(decision.value)
        async with transaction(self._session):
            meeting, participant = await self._lock_participant(caller)
            if participant.is_removed:
                raise ParticipantRemoved()
            meeting.ensure_in_progress()
            if not meeting.analysis_enabled:
                raise AnalysisDisabled()
            if decision is ConsentChange.GRANTED and notice_version is not None:
                check_notice_version(notice_version, notice=CURRENT_NOTICE)
            now = self._clock.now()
            if participant.consent_state is not state:
                participant = participant.with_consent(state)
                await self._participants.save_consent(participant.id, state, now=now)
                await self._journal.record(meeting, participant, origin, decided_at=now)
                await self._events.add(
                    consent_changed(participant, notice_version=CURRENT_NOTICE.version, decided_at=now), occurred_at=now
                )
            await self._queue.enqueue(participant, room_access(meeting, participant), now=now)

        synced = await self._sync.execute(participant_id=participant.id)
        return ConsentResult(state=state, synced=synced)

    async def _lock_participant(self, caller: OrganizerConsent | str) -> tuple[Meeting, Participant]:
        if isinstance(caller, OrganizerConsent):
            meeting = await self._meetings.lock_owned(caller.meeting_id, caller.user_id)
            if meeting is None:
                raise MeetingNotFound()
            participant = await self._participants.get_organizer(meeting.id, caller.user_id)
            if participant is None:
                meeting.ensure_in_progress()
                raise ParticipantNotFound()
            return meeting, participant

        guest = await self._participants.get_by_token_hash(hash_participant_token(caller))
        if guest is None:
            raise ParticipantTokenInvalid()
        meeting = await self._meetings.lock(guest.meeting_id)
        participant = await self._participants.get(guest.id, guest.meeting_id)
        if meeting is None or participant is None:
            raise ParticipantTokenInvalid()
        return meeting, participant
