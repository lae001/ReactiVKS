"""``POST /webhooks/livekit`` – вебхуки LiveKit (только из внутренней сети, Nginx его не проксирует)."""

from __future__ import annotations

from fastapi import APIRouter, status
from starlette.requests import Request

from meeting_service.api.v1.dependencies import HandleLiveKitWebhookScenario
from meeting_service.domain.errors import WebhookRejected

__all__ = ["router"]

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/livekit",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Вебхук LiveKit",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Подпись не LiveKit"}},
)
async def receive_livekit_webhook(request: Request, scenario: HandleLiveKitWebhookScenario) -> None:
    """`participant_joined`, `participant_left`, `room_finished`; остальные события принимаются и пропускаются."""
    # публичный: подлинность – подпись LiveKit в Authorization (JWT ключом API с SHA-256 тела).
    try:
        body = (await request.body()).decode("utf-8")
    except UnicodeDecodeError as error:
        raise WebhookRejected("Webhook body is not UTF-8") from error
    await scenario.execute(body=body, authorization=request.headers.get("authorization", ""))
