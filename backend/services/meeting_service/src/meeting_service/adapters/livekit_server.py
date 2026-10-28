"""``LiveKitGateway`` над Server API LiveKit (пакет ``livekit-api``).

Параметры вызовов – conventions.md, §5: таймаут 3 с, два повтора идемпотентных операций (``CreateRoom``
идемпотентна по имени, ``DeleteRoom`` – по смыслу) с задержкой 100 и 400 мс. После повторов –
:class:`LiveKitUnavailable` (``503 livekit_unavailable``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import TypeVar

import aiohttp
from livekit import api

from meeting_service.domain.errors import LiveKitUnavailable
from meeting_service.domain.livekit import (
    MAX_ROOM_PARTICIPANTS,
    ROOM_DEPARTURE_TIMEOUT_SECONDS,
    ROOM_EMPTY_TIMEOUT_SECONDS,
    RoomAccess,
)
from vks_common.logging import get_logger

__all__ = ["LiveKitServerGateway"]

_logger = get_logger(__name__)

_T = TypeVar("_T")

# Что участник может публиковать: камера, микрофон и демонстрация экрана со звуком.
_PUBLISH_SOURCES = ["camera", "microphone", "screen_share", "screen_share_audio"]
_RETRY_DELAYS_SECONDS = (0.1, 0.4)
# Ошибки сервера (5xx) и сети – повод повторить; 4xx – ошибка запроса, повтор ее не исправит.
_SERVER_ERROR_STATUS = 500


class LiveKitServerGateway:
    """Создается в ``lifespan`` (внутри работающего цикла событий) и закрывается при остановке."""

    def __init__(
        self,
        *,
        url: str,
        public_url: str,
        api_key: str,
        api_secret: str,
        token_ttl: timedelta,
        timeout_seconds: float,
        retry_delays: Sequence[float] = _RETRY_DELAYS_SECONDS,
    ) -> None:
        self._public_url = public_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._token_ttl = token_ttl
        self._retry_delays = tuple(retry_delays)
        # failover – переключение между регионами LiveKit Cloud; у собственного сервера регион один, а повторы
        # делаются здесь по правилам проекта.
        self._api = api.LiveKitAPI(
            url,
            api_key,
            api_secret,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            failover=False,
        )

    @property
    def public_url(self) -> str:
        return self._public_url

    async def ensure_room(self, room: str) -> None:
        request = api.CreateRoomRequest(
            name=room,
            empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
            departure_timeout=ROOM_DEPARTURE_TIMEOUT_SECONDS,
            max_participants=MAX_ROOM_PARTICIPANTS,
        )
        await self._call("CreateRoom", lambda: self._api.room.create_room(request))

    async def delete_room(self, room: str) -> None:
        try:
            await self._call("DeleteRoom", lambda: self._api.room.delete_room(api.DeleteRoomRequest(room=room)))
        except api.TwirpError as error:
            # Комнаты уже нет (закрылась по empty_timeout) – цель достигнута.
            if error.code != api.TwirpErrorCode.NOT_FOUND:
                raise

    def issue_token(self, access: RoomAccess) -> str:
        grants = api.VideoGrants(
            room_join=True,
            room=access.room,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            # Атрибуты (роль, согласие) выставляет только meeting-service: иначе участник объявил бы себе согласие.
            can_update_own_metadata=False,
            can_publish_sources=list(_PUBLISH_SOURCES),
        )
        token = (
            api.AccessToken(self._api_key, self._api_secret)
            .with_identity(access.identity)
            .with_name(access.name)
            .with_ttl(self._token_ttl)
            .with_grants(grants)
            .with_attributes(dict(access.attributes))
        )
        return token.to_jwt()

    async def check(self) -> None:
        """Проверка для ``/ready``: Server API отвечает на ``ListRooms``."""
        await self._api.room.list_rooms(api.ListRoomsRequest())

    async def aclose(self) -> None:
        await self._api.aclose()

    async def _call(self, operation: str, send: Callable[[], Awaitable[_T]]) -> _T:
        attempts = len(self._retry_delays) + 1
        for attempt in range(attempts):
            try:
                return await send()
            except (aiohttp.ClientError, TimeoutError) as error:
                failure: Exception = error
            except api.TwirpError as error:
                if error.status < _SERVER_ERROR_STATUS:
                    raise
                failure = error
            _logger.warning(
                "livekit call failed",
                operation=operation,
                attempt=attempt + 1,
                error=type(failure).__name__,
            )
            if attempt < len(self._retry_delays):
                await asyncio.sleep(self._retry_delays[attempt])
        raise LiveKitUnavailable() from failure
