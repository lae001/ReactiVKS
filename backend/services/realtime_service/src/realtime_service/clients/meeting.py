"""Внутренний HTTP API встреч и кеш проверки доступа."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from realtime_service.domain.meeting import MeetingSnapshot, ParticipantRole, ParticipantSnapshot
from vks_common.logging import get_logger

_logger = get_logger(__name__)


class _AccessResponse(BaseModel):
    allowed: bool


class _ParticipantResponse(BaseModel):
    id: UUID
    display_name: str
    role: ParticipantRole
    consent_state: Literal["granted", "denied", "revoked", "not_required"]
    online: bool
    is_removed: bool
    updated_at: AwareDatetime
    last_joined_at: AwareDatetime | None
    last_left_at: AwareDatetime | None


class _SnapshotResponse(BaseModel):
    owner_id: UUID
    status: Literal["scheduled", "active", "ended", "cancelled"]
    analysis_enabled: bool
    participants: list[_ParticipantResponse]


class MeetingClient:
    def __init__(self, http: httpx.AsyncClient, redis: Redis | None) -> None:
        self._http = http
        self._redis = redis

    async def is_allowed(self, meeting_id: UUID, user_id: UUID) -> bool:
        key = f"realtime:access:{meeting_id}:{user_id}"
        if self._redis is not None:
            try:
                cached: object = await self._redis.get(key)
                if isinstance(cached, bytes) and cached in (b"1", b"0"):
                    return cached == b"1"
            except RedisError as error:
                _logger.warning("access cache read failed", error=type(error).__name__)
        try:
            response = await self._http.get(f"/internal/meetings/{meeting_id}/access", params={"user_id": str(user_id)})
            response.raise_for_status()
            allowed = _AccessResponse.model_validate_json(response.content).allowed
        except (httpx.HTTPError, ValidationError) as error:
            _logger.warning("meeting access check failed", error=type(error).__name__)
            return False
        if self._redis is not None:
            try:
                await self._redis.set(key, "1" if allowed else "0", ex=60)
            except RedisError as error:
                _logger.warning("access cache write failed", error=type(error).__name__)
        return allowed

    async def snapshot(self, meeting_id: UUID) -> MeetingSnapshot | None:
        try:
            response = await self._http.get(f"/internal/meetings/{meeting_id}")
            response.raise_for_status()
            snapshot = _SnapshotResponse.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as error:
            _logger.warning("meeting snapshot unavailable", error=type(error).__name__)
            return None
        return MeetingSnapshot(
            owner_id=snapshot.owner_id,
            is_analyzed=snapshot.status == "active" and snapshot.analysis_enabled,
            is_closed=snapshot.status in ("ended", "cancelled"),
            participants=tuple(
                ParticipantSnapshot(
                    id=participant.id,
                    display_name=participant.display_name,
                    role=participant.role,
                    has_consent=participant.consent_state == "granted",
                    is_online=participant.online,
                    is_removed=participant.is_removed,
                    updated_at=participant.updated_at,
                    presence_at=max(
                        (at for at in (participant.last_joined_at, participant.last_left_at) if at is not None),
                        default=None,
                    ),
                )
                for participant in snapshot.participants
            ),
        )
