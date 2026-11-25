"""Административные маршруты meeting-service."""

from typing import Annotated

from fastapi import APIRouter, Query
from starlette.requests import Request

from meeting_service.api.v1.dependencies import CurrentClock, Session, Settings
from meeting_service.clients.health import read_health
from meeting_service.domain.errors import LiveKitUnavailable
from meeting_service.domain.meetings import InvalidCursor, MeetingCursor, MeetingQuery, MeetingStatus
from meeting_service.schemas.admin import AdminHealth, AdminMeeting, AdminMeetingPage
from meeting_service.schemas.meetings import MeetingResponse, MeetingStatusValue
from meeting_service.services.admin import list_admin_meetings
from vks_common.auth import CurrentAdmin
from vks_common.errors import ValidationFailed

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/meetings")
async def meetings(
    admin: CurrentAdmin,
    session: Session,
    settings: Settings,
    status: MeetingStatusValue | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> AdminMeetingPage:
    try:
        after = MeetingCursor.decode(cursor) if cursor else None
    except InvalidCursor as error:
        raise ValidationFailed("Invalid cursor", field="cursor") from error
    query = MeetingQuery(statuses=frozenset([MeetingStatus(status)]) if status else frozenset())
    page, counts = await list_admin_meetings(session, query, limit, after)
    return AdminMeetingPage(
        items=[
            AdminMeeting(
                **MeetingResponse.from_domain(
                    item, invite_url=settings.invite_url(item.meeting.invite_code)
                ).model_dump(),
                owner_id=item.meeting.owner_id,
                online_participants=counts.get(item.meeting.id, 0),
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor.encode() if page.next_cursor else None,
    )


@router.get("/health", response_model_exclude_none=True)
async def health(admin: CurrentAdmin, request: Request, settings: Settings, clock: CurrentClock) -> AdminHealth:
    catalog = request.app.state.livekit
    try:
        rooms = await catalog.list_rooms()
    except LiveKitUnavailable:
        rooms = None
    result = await read_health(
        settings,
        request.app.state.health,
        request.app.state.health_client,
        clock,
        request.app.state.ml_heartbeat.latest,
    )
    if rooms is not None:
        result.components["livekit"].rooms = len(rooms)
        result.components["livekit"].participants = sum(rooms.values())
    return AdminHealth.model_validate(result, from_attributes=True)
