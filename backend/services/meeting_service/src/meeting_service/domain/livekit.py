"""Порт LiveKit – единственная точка зависимости плоскости управления от медиасервера (требование заменяемости).

Права и атрибуты участника – livekit-integration.md; домен решает, что выдать, адаптер – как подписать.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from meeting_service.domain.identifiers import MeetingId, ParticipantId
from meeting_service.domain.meetings import Meeting
from meeting_service.domain.participants import Participant

__all__ = [
    "MAX_ROOM_PARTICIPANTS",
    "ROOM_DEPARTURE_TIMEOUT_SECONDS",
    "ROOM_EMPTY_TIMEOUT_SECONDS",
    "LeaveReason",
    "LiveKitGateway",
    "RoomAccess",
    "RoomEvent",
    "RoomEventKind",
    "WebhookVerifier",
    "meeting_id_of_room",
    "participant_id_of_identity",
    "room_access",
    "room_name",
]

# Комната без участников закрывается через 5 минут, ушедший участник ждет переподключения 20 с.
ROOM_EMPTY_TIMEOUT_SECONDS = 300
ROOM_DEPARTURE_TIMEOUT_SECONDS = 20
# Не более 10 человек одновременно; одиннадцатое место – ML-агент.
MAX_ROOM_PARTICIPANTS = 11


@dataclass(frozen=True, slots=True)
class RoomAccess:
    """Что разрешить участнику в комнате и какие атрибуты ему выставить."""

    room: str
    identity: str
    name: str
    attributes: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class LiveKitGateway(Protocol):
    """Что сценариям нужно от медиасервера."""

    @property
    def public_url(self) -> str:
        """Адрес сигнализации, к которому подключается браузер участника."""
        ...

    async def ensure_room(self, room: str) -> None:
        """Создать комнату, если ее нет (``CreateRoom`` идемпотентна по имени). ``LiveKitUnavailable`` – недоступен."""
        ...

    async def delete_room(self, room: str) -> None:
        """Закрыть комнату и отключить участников; несуществующая комната – не ошибка."""
        ...

    def issue_token(self, access: RoomAccess) -> str:
        """Токен доступа участника к комнате (подписывается локально, без сети)."""
        ...


class RoomEventKind(StrEnum):
    """Вебхуки, на которые реагирует meeting-service (livekit-integration.md, «Вебхуки»); прочие – ``OTHER``."""

    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    ROOM_FINISHED = "room_finished"
    OTHER = "other"


class LeaveReason(StrEnum):
    """Причина выхода в ``participant.left``."""

    LEFT = "left"
    REMOVED = "removed"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class RoomEvent:
    """Вебхук LiveKit с проверенной подписью – только то, что нужно сценарию.

    ``occurred_at`` – момент события по часам LiveKit; ``None`` – сервер его не передал.
    """

    event_id: str
    kind: RoomEventKind
    room: str
    occurred_at: datetime | None = None
    identity: str | None = None
    is_agent: bool = False
    leave_reason: LeaveReason = LeaveReason.LEFT


@runtime_checkable
class WebhookVerifier(Protocol):
    """Проверка подписи вебхука LiveKit (локально, без сети)."""

    def parse(self, body: str, authorization: str) -> RoomEvent:
        """Событие из тела вебхука. Подпись не та или тело изменено – ``WebhookRejected``."""
        ...


def room_name(meeting: Meeting) -> str:
    """Имя комнаты LiveKit – идентификатор встречи."""
    return str(meeting.id)


def room_access(meeting: Meeting, participant: Participant) -> RoomAccess:
    """Доступ участника: роль и согласие – атрибутами, которые сам участник изменить не может.

    По ``vks.consent`` ML-агент решает, подписываться ли на видео участника, поэтому атрибут выставляет только
    meeting-service.
    """
    return RoomAccess(
        room=room_name(meeting),
        identity=participant.livekit_identity,
        name=participant.display_name,
        attributes={
            "vks.role": participant.role.value,
            "vks.consent": participant.consent_state.value,
            "vks.kind": "human",
        },
    )


def meeting_id_of_room(room: str) -> MeetingId | None:
    """Встреча по имени комнаты; комната не наша (имя – не UUID) – ``None``."""
    try:
        return MeetingId(UUID(room))
    except ValueError:
        return None


def participant_id_of_identity(identity: str | None) -> ParticipantId | None:
    """Участник по identity ``p_<id>``; чужой формат (агент, тестовый клиент) – ``None``."""
    if identity is None or not identity.startswith("p_"):
        return None
    try:
        return ParticipantId(UUID(identity.removeprefix("p_")))
    except ValueError:
        return None
