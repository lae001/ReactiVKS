"""Эндпоинты ``/api/v1/join/{invite_code}`` – лобби и вход гостя (без аутентификации)."""

from __future__ import annotations

from fastapi import APIRouter, status

from meeting_service.api.v1.dependencies import GetJoinInfoScenario, JoinAsGuestScenario, Origin
from meeting_service.domain.consent import ConsentDecision
from meeting_service.schemas.join import GuestJoinRequest, GuestJoinResponse, JoinInfoResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/join",
    tags=["join"],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Приглашение не найдено"}},
)


@router.get("/{invite_code}", summary="Информация для лобби")
async def read_join_info(invite_code: str, scenario: GetJoinInfoScenario) -> JoinInfoResponse:
    """`consent_notice` – null, если анализ во встрече выключен."""
    # TODO(EMO-69): 429 – ограничение частоты по IP (Redis): код приглашения не должен перебираться.
    info = await scenario.execute(invite_code=invite_code)
    return JoinInfoResponse.from_domain(info.meeting, info.consent_notice)


@router.post(
    "/{invite_code}",
    summary="Вход гостя",
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "meeting_not_started (повторить через 5 с) | meeting_ended | meeting_cancelled | "
            "consent_required | notice_outdated"
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "livekit_unavailable"},
    },
)
async def join_as_guest(
    invite_code: str, body: GuestJoinRequest, scenario: JoinAsGuestScenario, origin: Origin
) -> GuestJoinResponse:
    """`participant_token` – для `Authorization: Participant <токен>`; `livekit_token` – только для медиа."""
    result = await scenario.execute(
        invite_code=invite_code,
        display_name=body.display_name,
        consent=ConsentDecision(body.consent) if body.consent is not None else None,
        notice_version=body.notice_version,
        origin=origin,
    )
    join = result.join
    return GuestJoinResponse.for_guest(
        join.meeting,
        join.participant,
        livekit_url=join.livekit_url,
        livekit_token=join.livekit_token,
        participant_token=result.participant_token,
    )
