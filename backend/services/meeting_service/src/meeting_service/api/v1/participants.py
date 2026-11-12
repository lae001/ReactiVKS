"""Эндпоинты ``/api/v1/participants/me`` – действия участника встречи."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from meeting_service.api.v1.dependencies import (
    ChangeConsentScenario,
    ConsentCaller,
    GuestToken,
    Origin,
    RejoinAsGuestScenario,
)
from meeting_service.schemas.join import JoinResultResponse
from meeting_service.schemas.participants import ChangeConsentRequest, ConsentResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/participants",
    tags=["participants"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет токена участника или он неизвестен"}},
)


@router.post(
    "/me/rejoin",
    summary="Новый токен LiveKit",
    responses={status.HTTP_409_CONFLICT: {"description": "meeting_ended | participant_removed | meeting_full"}},
)
async def rejoin(token: GuestToken, scenario: RejoinAsGuestScenario) -> JoinResultResponse:
    """Гость после перезагрузки вкладки получает новый токен LiveKit, не проходя лобби заново."""
    result = await scenario.execute(participant_token=token)
    return JoinResultResponse.from_domain(
        result.meeting, result.participant, livekit_url=result.livekit_url, livekit_token=result.livekit_token
    )


@router.put(
    "/me/consent",
    summary="Изменение согласия на анализ эмоций",
    responses={
        status.HTTP_202_ACCEPTED: {"model": ConsentResponse, "description": "Синхронизация с LiveKit в очереди"},
        status.HTTP_409_CONFLICT: {"description": "analysis_disabled | meeting_ended | participant_removed"},
    },
)
async def change_consent(
    body: ChangeConsentRequest,
    response: Response,
    caller: ConsentCaller,
    origin: Origin,
    scenario: ChangeConsentScenario,
) -> ConsentResponse:
    result = await scenario.execute(
        caller=caller, decision=body.decision, notice_version=body.notice_version, origin=origin
    )
    if not result.synced:
        response.status_code = status.HTTP_202_ACCEPTED
    return ConsentResponse(consent_state=result.state, synced=result.synced)
