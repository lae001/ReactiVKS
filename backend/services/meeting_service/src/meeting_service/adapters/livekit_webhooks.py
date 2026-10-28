"""``WebhookVerifier`` над ``WebhookReceiver`` LiveKit: подпись – JWT ключом API, в нем SHA-256 тела."""

from __future__ import annotations

from datetime import UTC, datetime

from livekit import api
from livekit.protocol.models import DisconnectReason, ParticipantInfo

from meeting_service.domain.errors import WebhookRejected
from meeting_service.domain.livekit import LeaveReason, RoomEvent, RoomEventKind

__all__ = ["LiveKitWebhookVerifier"]

_KINDS = {kind.value: kind for kind in RoomEventKind if kind is not RoomEventKind.OTHER}
# Выход по инициативе участника и удаление организатором; все прочие причины – обрыв связи или закрытие комнаты.
_LEAVE_REASONS = {
    DisconnectReason.CLIENT_INITIATED: LeaveReason.LEFT,
    DisconnectReason.PARTICIPANT_REMOVED: LeaveReason.REMOVED,
}


class LiveKitWebhookVerifier:
    """Создается при сборке приложения: проверка подписи не ходит в сеть и цикла событий не требует."""

    def __init__(self, *, api_key: str, api_secret: str) -> None:
        self._receiver = api.WebhookReceiver(api.TokenVerifier(api_key, api_secret))

    def parse(self, body: str, authorization: str) -> RoomEvent:
        try:
            event = self._receiver.receive(body, authorization)
        # WebhookReceiver сообщает о несовпадении хеша голым Exception, о плохом JWT – исключениями pyjwt, о
        # неразборчивом теле – protobuf: для вызывающего все это одно – вебхуку верить нельзя.
        except Exception as error:
            raise WebhookRejected("LiveKit webhook signature is not valid") from error
        participant: ParticipantInfo = event.participant
        is_agent = participant.kind == ParticipantInfo.Kind.AGENT or participant.attributes.get("vks.kind") == "agent"
        return RoomEvent(
            # LiveKit всегда присылает id; запасной ключ – чтобы дедупликация не склеила разные события без него.
            event_id=event.id or f"{event.event}:{event.room.name}:{participant.identity}:{event.created_at}",
            kind=_KINDS.get(event.event, RoomEventKind.OTHER),
            room=event.room.name,
            occurred_at=datetime.fromtimestamp(event.created_at, tz=UTC) if event.created_at else None,
            identity=participant.identity or None,
            is_agent=is_agent,
            leave_reason=_LEAVE_REASONS.get(participant.disconnect_reason, LeaveReason.DISCONNECTED),
        )
