"""Корень сборки realtime-service."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from realtime_service.api.websocket import router
from realtime_service.clients.meeting import MeetingClient
from realtime_service.consumers.events import consume_events
from realtime_service.services.live_rooms import LiveRooms
from realtime_service.settings import RealtimeSettings
from vks_common.app import create_app
from vks_common.auth import JwksKeys, TokenVerifier, use_authentication
from vks_common.clock import SystemClock
from vks_common.kafka import log_unexpected_stop


def create_application(settings: RealtimeSettings | None = None) -> FastAPI:
    resolved = settings or RealtimeSettings.load()
    jwks = httpx.AsyncClient(timeout=2.0)
    rooms = LiveRooms()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis = (
            Redis.from_url(
                resolved.redis_url,
                password=resolved.redis_password.get_secret_value() if resolved.redis_password is not None else None,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
            if resolved.redis_url
            else None
        )
        async with httpx.AsyncClient(
            base_url=resolved.meeting_url,
            headers={"X-Service-Token": resolved.service_token.get_secret_value()},
            timeout=2.0,
        ) as http:
            app.state.meetings = MeetingClient(http, redis)
            task = asyncio.create_task(
                consume_events(rooms, bootstrap_servers=resolved.kafka_bootstrap_servers, instance=resolved.instance),
                name="realtime-events",
            )
            task.add_done_callback(log_unexpected_stop)
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if redis is not None:
                    await redis.aclose()
                await jwks.aclose()

    app = create_app(resolved, routers=[router], lifespan=lifespan, title="ReactiVKS realtime-service")
    app.state.clock = SystemClock()
    app.state.rooms = rooms
    use_authentication(
        app,
        TokenVerifier(
            keys=JwksKeys(resolved.jwks_url, http_client=jwks),
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            leeway_seconds=resolved.jwt_leeway_seconds,
        ),
    )
    return app
