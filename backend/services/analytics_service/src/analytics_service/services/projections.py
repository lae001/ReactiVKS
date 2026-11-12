"""Применение событий встреч и учетных записей."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics_service.repositories.projections import Projections
from vks_common.db import transaction
from vks_common.kafka.consumer import TemporaryFailure
from vks_contracts import ParsedEvent
from vks_contracts.meeting_events import (
    ConsentChanged,
    MeetingCancelled,
    MeetingCreated,
    MeetingDeleted,
    MeetingEnded,
    MeetingStarted,
    MeetingUpdated,
    ParticipantRegistered,
)
from vks_contracts.user_events import UserDeleted


class ProjectEvents:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def execute(self, event: ParsedEvent) -> None:
        payload = event.payload
        at = event.envelope.occurred_at
        try:
            async with self._sessions() as session, transaction(session):
                projections = Projections(session)
                if isinstance(payload, (MeetingCreated, MeetingStarted)):
                    await projections.put_meeting(
                        payload.meeting_id,
                        payload.owner_id,
                        payload.title,
                        is_analyzed=payload.analysis_enabled,
                        at=at,
                        started_at=payload.started_at if isinstance(payload, MeetingStarted) else None,
                    )
                elif isinstance(payload, MeetingUpdated):
                    await projections.update_meeting(
                        payload.meeting_id, at, title=payload.title, analysis_enabled=payload.analysis_enabled
                    )
                elif isinstance(payload, MeetingEnded):
                    await projections.update_meeting(payload.meeting_id, at, status="ended", ended_at=payload.ended_at)
                elif isinstance(payload, MeetingCancelled):
                    await projections.update_meeting(payload.meeting_id, at, status="cancelled")
                elif isinstance(payload, ParticipantRegistered):
                    await projections.register(
                        payload.meeting_id,
                        payload.participant_id,
                        payload.display_name,
                        payload.role,
                        payload.consent_state,
                        at=at,
                    )
                elif isinstance(payload, ConsentChanged):
                    await projections.change_consent(
                        payload.meeting_id, payload.participant_id, payload.consent_state, at=payload.decided_at
                    )
                elif isinstance(payload, MeetingDeleted):
                    await projections.remove_meeting(payload.meeting_id)
                elif isinstance(payload, UserDeleted):
                    await projections.remove_owner(payload.user_id)
        except SQLAlchemyError as error:
            raise TemporaryFailure("analytics projection database unavailable") from error
