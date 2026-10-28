"""Эндпоинты ``/api/v1/meetings`` (docs/api/rest-api.md, раздел 3) – встречи организатора (Bearer)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query, status
from fastapi.exceptions import RequestValidationError

from meeting_service.api.v1.dependencies import (
    CallingOrganizer,
    CreateMeetingScenario,
    EndMeetingScenario,
    GetMeetingScenario,
    JoinAsOrganizerScenario,
    ListMeetingsScenario,
    Origin,
    Settings,
)
from meeting_service.domain.consent import ConsentDecision
from meeting_service.domain.identifiers import MeetingId
from meeting_service.domain.meetings import InvalidCursor, MeetingCursor, MeetingOverview, MeetingQuery, MeetingStatus
from meeting_service.schemas.join import JoinResultResponse, OrganizerJoinRequest
from meeting_service.schemas.meetings import CreateMeetingRequest, MeetingPageResponse, MeetingResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/meetings",
    tags=["meetings"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет access-токена или он недействителен"}},
)

_NOT_FOUND: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Встречи нет или она чужая"}
}
_STATUSES = "|".join(item.value for item in MeetingStatus)
_STATUS_LIST_PATTERN = rf"^({_STATUSES})(,({_STATUSES}))*$"


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать встречу",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Название, время или частота анализа"}},
)
async def create_meeting(
    body: CreateMeetingRequest, organizer: CallingOrganizer, scenario: CreateMeetingScenario, settings: Settings
) -> MeetingResponse:
    """Встреча создается в статусе `scheduled` и активируется первым входом организатора."""
    # TODO(EMO-68): заголовок Idempotency-Key (ключ и ответ – в Redis на 24 ч).
    overview = await scenario.execute(
        organizer=organizer,
        title=body.title,
        scheduled_at=body.scheduled_at,
        analysis_enabled=body.analysis_enabled,
        analysis_fps=body.analysis_fps,
    )
    return _response(overview, settings)


@router.get("", summary="История и запланированные встречи")
async def list_meetings(
    organizer: CallingOrganizer,
    scenario: ListMeetingsScenario,
    settings: Settings,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern=_STATUS_LIST_PATTERN, description="Статусы через запятую"),
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="Подстрока названия")] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> MeetingPageResponse:
    """Новые сверху: по моменту начала, иначе по плановому времени, иначе по созданию. Удаленные не возвращаются."""
    query = MeetingQuery(
        statuses=frozenset(MeetingStatus(value) for value in status_filter.split(","))
        if status_filter
        else frozenset(),
        text=(q.strip() or None) if q else None,
        date_from=date_from,
        date_to=date_to,
    )
    page = await scenario.execute(
        owner_id=organizer.user_id,
        query=query,
        limit=limit,
        after=_decode_cursor(cursor) if cursor else None,
    )
    return MeetingPageResponse(
        items=[_response(overview, settings) for overview in page.items],
        next_cursor=page.next_cursor.encode() if page.next_cursor is not None else None,
    )


@router.get("/{meeting_id}", summary="Карточка встречи", responses=_NOT_FOUND)
async def read_meeting(
    meeting_id: UUID, organizer: CallingOrganizer, scenario: GetMeetingScenario, settings: Settings
) -> MeetingResponse:
    overview = await scenario.execute(owner_id=organizer.user_id, meeting_id=MeetingId(meeting_id))
    return _response(overview, settings)


@router.post(
    "/{meeting_id}/join",
    summary="Вход организатора",
    responses={
        **_NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "meeting_ended | meeting_cancelled | consent_required"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "livekit_unavailable"},
    },
)
async def join_meeting(
    meeting_id: UUID,
    organizer: CallingOrganizer,
    scenario: JoinAsOrganizerScenario,
    origin: Origin,
    body: Annotated[OrganizerJoinRequest | None, Body()] = None,
) -> JoinResultResponse:
    """Первый вход активирует встречу (`scheduled → active`) и создает комнату LiveKit.

    Решение о согласии обязательно, если в встрече включен анализ эмоций.
    """
    # TODO(EMO-69): 403 user_blocked – по проекции блокировок из user.events.
    consent = body.consent if body is not None else None
    result = await scenario.execute(
        organizer=organizer,
        meeting_id=MeetingId(meeting_id),
        consent=ConsentDecision(consent) if consent is not None else None,
        origin=origin,
    )
    return JoinResultResponse.from_domain(
        result.meeting,
        result.participant,
        livekit_url=result.livekit_url,
        livekit_token=result.livekit_token,
    )


@router.post(
    "/{meeting_id}/end",
    summary="Завершить встречу",
    responses={**_NOT_FOUND, status.HTTP_409_CONFLICT: {"description": "meeting_cancelled | meeting_not_started"}},
)
async def end_meeting(
    meeting_id: UUID, organizer: CallingOrganizer, scenario: EndMeetingScenario, settings: Settings
) -> MeetingResponse:
    """Идемпотентно: завершенная встреча возвращается как есть. Участники отключаются от комнаты."""
    overview = await scenario.execute(owner_id=organizer.user_id, meeting_id=MeetingId(meeting_id))
    return _response(overview, settings)


def _response(overview: MeetingOverview, settings: Settings) -> MeetingResponse:
    return MeetingResponse.from_domain(overview, invite_url=settings.invite_url(overview.meeting.invite_code))


def _decode_cursor(value: str) -> MeetingCursor:
    try:
        return MeetingCursor.decode(value)
    except InvalidCursor as error:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "Cursor is not valid", "type": "value_error"}]
        ) from error
