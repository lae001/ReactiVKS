"""Встречи: ``meeting.meetings``.

Каждый запрос организатора ограничен владельцем в самом SQL (``owner_id = :sub``): чужая встреча для него не
существует, и пагинация не ломается фильтрацией после выборки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import ColumnElement, Select, Uuid, func, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.domain.meetings import (
    EndReason,
    Meeting,
    MeetingCursor,
    MeetingOverview,
    MeetingQuery,
    MeetingStatus,
)
from meeting_service.models import MeetingRow, ParticipantRow
from vks_common.db import is_unique_violation

__all__ = ["InviteCodeTaken", "MeetingPage", "MeetingRepository"]

_INVITE_CODE_UNIQUE_CONSTRAINT = "meetings_invite_code_uk"


class InviteCodeTaken(Exception):
    """Случайный код приглашения совпал с существующим – сценарий выбирает другой."""


# Момент встречи для сортировки и фильтра по датам: когда началась, иначе на когда назначена, иначе когда создана.
_MOMENT = func.coalesce(MeetingRow.started_at, MeetingRow.scheduled_at, MeetingRow.created_at)

_PARTICIPANTS_COUNT = (
    select(func.count(ParticipantRow.id))
    .where(ParticipantRow.meeting_id == MeetingRow.id)
    .correlate(MeetingRow)
    .scalar_subquery()
)


@dataclass(frozen=True, slots=True)
class MeetingPage:
    """Страница истории и курсор следующей (``None`` – страница последняя)."""

    items: list[MeetingOverview]
    next_cursor: MeetingCursor | None


class MeetingRepository:
    """Работает в транзакции вызывающего сценария; сам не коммитит."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, meeting: Meeting) -> None:
        """Добавить встречу. Совпавший код приглашения – :class:`InviteCodeTaken`."""
        self._session.add(
            MeetingRow(
                id=meeting.id,
                owner_id=meeting.owner_id,
                owner_name=meeting.owner_name,
                title=meeting.title,
                invite_code=meeting.invite_code,
                status=meeting.status.value,
                analysis_enabled=meeting.analysis_enabled,
                analysis_fps=meeting.analysis_fps,
                scheduled_at=meeting.scheduled_at,
                started_at=meeting.started_at,
                ended_at=meeting.ended_at,
                end_reason=meeting.end_reason.value if meeting.end_reason is not None else None,
                created_at=meeting.created_at,
                updated_at=meeting.created_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if is_unique_violation(error, constraint=_INVITE_CODE_UNIQUE_CONSTRAINT):
                raise InviteCodeTaken() from error
            raise

    async def get_owned(self, meeting_id: MeetingId, owner_id: UserId) -> Meeting | None:
        row = (await self._session.execute(_owned(meeting_id, owner_id))).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def lock_owned(self, meeting_id: MeetingId, owner_id: UserId) -> Meeting | None:
        """Найти встречу организатора и заблокировать строку до конца транзакции.

        Смена статуса – под ``FOR UPDATE`` (conventions.md, §8): одновременные «войти» и «завершить» видят друг
        друга, а не одно и то же исходное состояние.
        """
        row = (await self._session.execute(_owned(meeting_id, owner_id).with_for_update())).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get(self, meeting_id: MeetingId) -> Meeting | None:
        """Без области владельца – для гостя, чье право на встречу подтверждено его токеном."""
        statement = select(MeetingRow).where(MeetingRow.id == meeting_id, MeetingRow.deleted_at.is_(None))
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_invite_code(self, invite_code: str) -> Meeting | None:
        statement = select(MeetingRow).where(
            MeetingRow.invite_code == invite_code,
            MeetingRow.deleted_at.is_(None),
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def save_lifecycle(self, meeting: Meeting, *, now: datetime) -> None:
        """Записать статус и его отметки времени."""
        await self._session.execute(
            update(MeetingRow)
            .where(MeetingRow.id == meeting.id)
            .values(
                status=meeting.status.value,
                started_at=meeting.started_at,
                ended_at=meeting.ended_at,
                end_reason=meeting.end_reason.value if meeting.end_reason is not None else None,
                updated_at=now,
            )
        )

    async def save_details(self, meeting: Meeting, *, now: datetime) -> None:
        """Записать название, время и параметры анализа."""
        await self._session.execute(
            update(MeetingRow)
            .where(MeetingRow.id == meeting.id)
            .values(
                title=meeting.title,
                scheduled_at=meeting.scheduled_at,
                analysis_enabled=meeting.analysis_enabled,
                analysis_fps=meeting.analysis_fps,
                updated_at=now,
            )
        )

    async def soft_delete(self, meeting_id: MeetingId, *, now: datetime) -> None:
        """Пометить удаленной: встреча пропадает из всех запросов, строку физически удалит очистка через 30 дней."""
        await self._session.execute(
            update(MeetingRow).where(MeetingRow.id == meeting_id).values(deleted_at=now, updated_at=now)
        )

    async def overview(self, meeting: Meeting) -> MeetingOverview:
        statement = select(func.count(ParticipantRow.id)).where(ParticipantRow.meeting_id == meeting.id)
        count = (await self._session.execute(statement)).scalar_one()
        return MeetingOverview(meeting=meeting, participants_count=count)

    async def list_owned(
        self,
        owner_id: UserId,
        query: MeetingQuery,
        *,
        limit: int,
        after: MeetingCursor | None,
    ) -> MeetingPage:
        """История организатора, новые сверху. Курсор – момент и ``id`` последней выданной встречи."""
        statement = (
            select(MeetingRow, _PARTICIPANTS_COUNT, _MOMENT)
            .where(MeetingRow.owner_id == owner_id, MeetingRow.deleted_at.is_(None), *_filters(query))
            .order_by(_MOMENT.desc(), MeetingRow.id.desc())
            # Лишняя строка показывает, есть ли следующая страница, без отдельного count.
            .limit(limit + 1)
        )
        if after is not None:
            position = tuple_(literal(after.sort_key, TIMESTAMP(timezone=True)), literal(after.meeting_id, Uuid()))
            statement = statement.where(tuple_(_MOMENT, MeetingRow.id) < position)
        rows = (await self._session.execute(statement)).all()
        items = [MeetingOverview(meeting=_to_domain(row), participants_count=count) for row, count, _ in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last_row, _, last_moment = rows[limit - 1]
            next_cursor = MeetingCursor(sort_key=last_moment, meeting_id=last_row.id)
        return MeetingPage(items=items, next_cursor=next_cursor)


def _owned(meeting_id: MeetingId, owner_id: UserId) -> Select[tuple[MeetingRow]]:
    return select(MeetingRow).where(
        MeetingRow.id == meeting_id,
        MeetingRow.owner_id == owner_id,
        MeetingRow.deleted_at.is_(None),
    )


def _filters(query: MeetingQuery) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if query.statuses:
        filters.append(MeetingRow.status.in_(sorted(status.value for status in query.statuses)))
    if query.text:
        # Подстрока ищется буквально: % и _ из запроса пользователя – символы, а не шаблоны LIKE.
        escaped = query.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(MeetingRow.title.ilike(f"%{escaped}%", escape="\\"))
    if query.date_from is not None:
        filters.append(_MOMENT >= datetime.combine(query.date_from, time.min, tzinfo=UTC))
    if query.date_to is not None:
        filters.append(_MOMENT < datetime.combine(query.date_to + timedelta(days=1), time.min, tzinfo=UTC))
    return filters


def _to_domain(row: MeetingRow) -> Meeting:
    return Meeting(
        id=MeetingId(row.id),
        owner_id=UserId(row.owner_id),
        owner_name=row.owner_name,
        title=row.title,
        invite_code=row.invite_code,
        status=MeetingStatus(row.status),
        analysis_enabled=row.analysis_enabled,
        analysis_fps=row.analysis_fps,
        scheduled_at=row.scheduled_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        end_reason=EndReason(row.end_reason) if row.end_reason is not None else None,
        created_at=row.created_at,
    )
