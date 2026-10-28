"""Эндпоинты ``/api/v1/meetings/{id}/participants`` – участники и модерация встречи (владелец, Bearer)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from meeting_service.api.v1.dependencies import (
    CallingOrganizer,
    ListParticipantsScenario,
    MuteParticipantScenario,
    RemoveParticipantScenario,
)
from meeting_service.domain.identifiers import MeetingId, ParticipantId
from meeting_service.domain.livekit import MediaKind
from meeting_service.schemas.participants import MuteRequest, ParticipantListResponse, ParticipantResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/meetings/{meeting_id}/participants",
    tags=["moderation"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Нет access-токена или он недействителен"},
        status.HTTP_404_NOT_FOUND: {"description": "Встречи нет, она чужая или в ней нет такого участника"},
    },
)

_MODERATION_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"description": "meeting_not_started | meeting_ended | meeting_cancelled"},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "livekit_unavailable"},
}


@router.get("", summary="Участники и согласия")
async def list_participants(
    meeting_id: UUID, organizer: CallingOrganizer, scenario: ListParticipantsScenario
) -> ParticipantListResponse:
    """В порядке регистрации; удаленные – с `is_removed = true`."""
    participants = await scenario.execute(owner_id=organizer.user_id, meeting_id=MeetingId(meeting_id))
    return ParticipantListResponse(items=[ParticipantResponse.from_domain(item) for item in participants])


@router.post(
    "/{participant_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выключить микрофон или камеру",
    responses=_MODERATION_ERRORS,
)
async def mute_participant(
    meeting_id: UUID,
    participant_id: UUID,
    body: MuteRequest,
    organizer: CallingOrganizer,
    scenario: MuteParticipantScenario,
) -> None:
    """Идемпотентно. Включить обратно может только сам участник."""
    await scenario.execute(
        owner_id=organizer.user_id,
        meeting_id=MeetingId(meeting_id),
        participant_id=ParticipantId(participant_id),
        kind=MediaKind(body.kind),
    )


@router.post(
    "/{participant_id}/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить из встречи",
    responses={
        **_MODERATION_ERRORS,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Организатора из своей встречи не удаляют"},
    },
)
async def remove_participant(
    meeting_id: UUID, participant_id: UUID, organizer: CallingOrganizer, scenario: RemoveParticipantScenario
) -> None:
    """Идемпотентно. Повторный вход по токену удаленного участника – `409 participant_removed`."""
    await scenario.execute(
        owner_id=organizer.user_id, meeting_id=MeetingId(meeting_id), participant_id=ParticipantId(participant_id)
    )
