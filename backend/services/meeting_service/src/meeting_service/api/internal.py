"""Внутреннее API для realtime и аналитики."""

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from meeting_service.api.v1.dependencies import Session, Settings
from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.schemas.internal import MeetingAccessResponse, MeetingSnapshotResponse, ParticipantSnapshotResponse
from meeting_service.schemas.meetings import MeetingResponse
from meeting_service.schemas.participants import ParticipantResponse
from meeting_service.services.internal import CheckMeetingAccess, ReadMeetingSnapshot
from vks_common.errors import Unauthorized


def require_service(settings: Settings, x_service_token: Annotated[str | None, Header()] = None) -> None:
    expected = settings.service_token
    if (
        expected is None
        or x_service_token is None
        or not secrets.compare_digest(x_service_token.encode(), expected.get_secret_value().encode())
    ):
        raise Unauthorized()


router = APIRouter(prefix="/internal/meetings", dependencies=[Depends(require_service)], include_in_schema=False)


@router.get("/{meeting_id}/access")
async def meeting_access(meeting_id: UUID, user_id: UUID, session: Session) -> MeetingAccessResponse:
    meeting = await CheckMeetingAccess(session).execute(MeetingId(meeting_id), UserId(user_id))
    if meeting is None:
        return MeetingAccessResponse(allowed=False)
    return MeetingAccessResponse(
        allowed=True, meeting_status=meeting.status.value, analysis_enabled=meeting.analysis_enabled
    )


@router.get("/{meeting_id}")
async def meeting_snapshot(meeting_id: UUID, session: Session, settings: Settings) -> MeetingSnapshotResponse:
    snapshot = await ReadMeetingSnapshot(session).execute(MeetingId(meeting_id))
    meeting = snapshot.overview.meeting
    response = MeetingResponse.from_domain(snapshot.overview, invite_url=settings.invite_url(meeting.invite_code))
    return MeetingSnapshotResponse(
        **response.model_dump(),
        owner_id=meeting.owner_id,
        participants=[
            ParticipantSnapshotResponse(
                **ParticipantResponse.from_domain(participant).model_dump(),
                updated_at=participant.updated_at or participant.created_at,
                last_joined_at=participant.last_joined_at,
            )
            for participant in snapshot.participants
        ],
    )
