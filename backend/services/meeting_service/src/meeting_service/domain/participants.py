"""Участник встречи и правила его полей."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from meeting_service.domain.errors import InvalidDisplayName
from meeting_service.domain.identifiers import MeetingId, ParticipantId, UserId

__all__ = [
    "MAX_DISPLAY_NAME_LENGTH",
    "PARTICIPANT_TOKEN_PREFIX",
    "ConsentState",
    "Participant",
    "ParticipantRole",
    "hash_participant_token",
    "normalize_display_name",
]

MAX_DISPLAY_NAME_LENGTH = 64
# Префикс отличает токен гостя от access-токена в заголовке и в случайно попавшем на глаза тексте.
PARTICIPANT_TOKEN_PREFIX = "pt_"  # noqa: S105 - префикс формата, а не секрет


class ParticipantRole(StrEnum):
    ORGANIZER = "organizer"
    GUEST = "guest"


class ConsentState(StrEnum):
    """Текущее решение участника об анализе эмоций; ``not_required`` – анализ во встрече выключен."""

    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"
    NOT_REQUIRED = "not_required"


@dataclass(frozen=True, slots=True)
class Participant:
    """Участник встречи: организатор (по учетной записи) или гость (по токену участника)."""

    id: ParticipantId
    meeting_id: MeetingId
    display_name: str
    role: ParticipantRole
    consent_state: ConsentState
    created_at: datetime
    user_id: UserId | None = None
    is_removed: bool = False

    @property
    def livekit_identity(self) -> str:
        """identity в комнате LiveKit (livekit-integration.md): по нему вебхуки находят участника."""
        return f"p_{self.id}"

    def with_consent(self, state: ConsentState) -> Participant:
        return replace(self, consent_state=state)


def normalize_display_name(raw: str) -> str:
    """Имя участника без пробелов по краям, от 1 до 64 символов."""
    name = raw.strip()
    if not name or len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise InvalidDisplayName(
            f"Display name must be 1 to {MAX_DISPLAY_NAME_LENGTH} characters long",
            field="display_name",
        )
    return name


def hash_participant_token(token: str) -> bytes:
    """Значение ``participants.participant_token_hash``. SHA-256 достаточно: токен – 256 случайных бит."""
    return hashlib.sha256(token.encode("utf-8")).digest()
