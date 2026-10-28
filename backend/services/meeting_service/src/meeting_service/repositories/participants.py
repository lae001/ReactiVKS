"""Участники: ``meeting.participants``.

Гость находится по хешу своего токена; сам токен существует один раз – в ответе, который его выдал.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import MeetingId, ParticipantId, UserId
from meeting_service.domain.participants import ConsentState, Participant, ParticipantRole
from meeting_service.models import ParticipantRow

__all__ = ["ParticipantRepository"]

# То же правило, что Participant.is_online, – в SQL, чтобы считать участников в комнате без выборки строк.
_ONLINE: ColumnElement[bool] = and_(
    ParticipantRow.is_removed.is_(False),
    ParticipantRow.last_joined_at.is_not(None),
    or_(ParticipantRow.last_left_at.is_(None), ParticipantRow.last_left_at < ParticipantRow.last_joined_at),
)


class ParticipantRepository:
    """Работает в транзакции вызывающего сценария; сам не коммитит."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, participant: Participant, *, token_hash: bytes | None = None) -> None:
        """Добавить участника. ``token_hash`` – только у гостя (``participants_identity_ck``)."""
        self._session.add(
            ParticipantRow(
                id=participant.id,
                meeting_id=participant.meeting_id,
                user_id=participant.user_id,
                display_name=participant.display_name,
                role=participant.role.value,
                consent_state=participant.consent_state.value,
                participant_token_hash=token_hash,
                is_removed=participant.is_removed,
                created_at=participant.created_at,
                updated_at=participant.created_at,
            )
        )
        await self._session.flush()

    async def get_organizer(self, meeting_id: MeetingId, user_id: UserId) -> Participant | None:
        """Организатор как участник своей встречи – одна строка, сколько бы раз он ни входил."""
        statement = select(ParticipantRow).where(
            ParticipantRow.meeting_id == meeting_id,
            ParticipantRow.user_id == user_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get(self, participant_id: ParticipantId, meeting_id: MeetingId) -> Participant | None:
        statement = select(ParticipantRow).where(
            ParticipantRow.id == participant_id, ParticipantRow.meeting_id == meeting_id
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_token_hash(self, token_hash: bytes) -> Participant | None:
        statement = select(ParticipantRow).where(ParticipantRow.participant_token_hash == token_hash)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def save_consent(self, participant_id: ParticipantId, state: ConsentState, *, now: datetime) -> None:
        await self._session.execute(
            update(ParticipantRow)
            .where(ParticipantRow.id == participant_id)
            .values(consent_state=state.value, updated_at=now)
        )

    async def mark_joined(self, participant_id: ParticipantId, *, at: datetime, now: datetime) -> None:
        """Отметить вход в комнату. ``least``/``greatest``: опоздавший вебхук не сдвигает отметки в неверную сторону."""
        await self._session.execute(
            update(ParticipantRow)
            .where(ParticipantRow.id == participant_id)
            .values(
                first_joined_at=func.least(ParticipantRow.first_joined_at, at),
                last_joined_at=func.greatest(ParticipantRow.last_joined_at, at),
                updated_at=now,
            )
        )

    async def mark_left(self, participant_id: ParticipantId, *, at: datetime, now: datetime) -> None:
        await self._session.execute(
            update(ParticipantRow)
            .where(ParticipantRow.id == participant_id)
            .values(last_left_at=func.greatest(ParticipantRow.last_left_at, at), updated_at=now)
        )

    async def count_online(self, meeting_id: MeetingId, *, excluding: ParticipantId | None = None) -> int:
        """Участники встречи, которые сейчас в комнате; ``excluding`` – не считать входящего повторно."""
        statement = select(func.count(ParticipantRow.id)).where(ParticipantRow.meeting_id == meeting_id, _ONLINE)
        if excluding is not None:
            statement = statement.where(ParticipantRow.id != excluding)
        return (await self._session.execute(statement)).scalar_one()


def _to_domain(row: ParticipantRow) -> Participant:
    return Participant(
        id=ParticipantId(row.id),
        meeting_id=MeetingId(row.meeting_id),
        user_id=UserId(row.user_id) if row.user_id is not None else None,
        display_name=row.display_name,
        role=ParticipantRole(row.role),
        consent_state=ConsentState(row.consent_state),
        is_removed=row.is_removed,
        created_at=row.created_at,
        first_joined_at=row.first_joined_at,
        last_joined_at=row.last_joined_at,
        last_left_at=row.last_left_at,
    )
