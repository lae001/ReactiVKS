"""Эндпоинты ``/api/v1/participants/me`` – действия гостя по его токену участника."""

from __future__ import annotations

from fastapi import APIRouter, status

from meeting_service.api.v1.dependencies import GuestToken, RejoinAsGuestScenario
from meeting_service.schemas.join import JoinResultResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/participants",
    tags=["participants"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет токена участника или он неизвестен"}},
)


@router.post(
    "/me/rejoin",
    summary="Новый токен LiveKit",
    responses={status.HTTP_409_CONFLICT: {"description": "meeting_ended | participant_removed"}},
)
async def rejoin(token: GuestToken, scenario: RejoinAsGuestScenario) -> JoinResultResponse:
    """Гость после перезагрузки вкладки получает новый токен LiveKit, не проходя лобби заново."""
    # TODO(EMO-84): PUT /participants/me/consent – изменение решения о согласии.
    result = await scenario.execute(participant_token=token)
    return JoinResultResponse.from_domain(
        result.meeting, result.participant, livekit_url=result.livekit_url, livekit_token=result.livekit_token
    )
