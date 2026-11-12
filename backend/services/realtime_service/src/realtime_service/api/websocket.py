"""Транспорт WebSocket vks.v1."""

import asyncio
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from realtime_service.schemas.websocket import ClientMessage
from realtime_service.services.connection import CloseConnection, PanelConnection
from realtime_service.services.live_rooms import Message

router = APIRouter()
_SUBPROTOCOL = "vks.v1"
_BATCH_SECONDS = 0.25
_PROTOCOL_ERRORS = {
    4400: ("invalid_message", "Invalid WebSocket message"),
    4401: ("unauthorized", "A valid access token is required"),
    4403: ("forbidden", "Access to the meeting was denied"),
}


def build_connection(websocket: WebSocket) -> PanelConnection:
    state = websocket.app.state
    return PanelConnection(
        clock=state.clock,
        verifier=state.token_verifier,
        meetings=state.meetings,
        rooms=state.rooms,
    )


@router.websocket("/ws")
async def panel(websocket: WebSocket, connection: Annotated[PanelConnection, Depends(build_connection)]) -> None:
    if _SUBPROTOCOL not in websocket.scope["subprotocols"]:
        await websocket.accept()
        await websocket.close(4400)
        return
    await websocket.accept(subprotocol=_SUBPROTOCOL)
    tasks = [
        asyncio.create_task(_read(websocket, connection)),
        asyncio.create_task(_write(websocket, connection)),
    ]
    closing: CloseConnection | None = None
    try:
        finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in finished:
            task.result()
    except CloseConnection as error:
        closing = error
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        connection.close()
    if closing is not None:
        with suppress(WebSocketDisconnect, TimeoutError):
            async with asyncio.timeout(2):
                await _close(websocket, closing)


async def _close(websocket: WebSocket, closing: CloseConnection) -> None:
    reason = _PROTOCOL_ERRORS.get(closing.code)
    if reason is not None:
        code, message = reason
        payload: Message = {"type": "error", "code": code, "message": message}
        if closing.request_id is not None:
            payload["id"] = closing.request_id
        await websocket.send_json(payload)
    await websocket.close(closing.code)


async def _read(websocket: WebSocket, connection: PanelConnection) -> None:
    while True:
        event = await websocket.receive()
        if event["type"] == "websocket.disconnect":
            raise WebSocketDisconnect()
        raw = event.get("text")
        if not isinstance(raw, str) or len(raw) > 8192:
            raise CloseConnection(4400)
        try:
            command = ClientMessage.model_validate_json(raw)
        except ValidationError as error:
            raise CloseConnection(4400) from error

        try:
            if not connection.is_authenticated and command.type != "auth":
                raise CloseConnection(4401)
            response = await _execute(connection, command)
        except CloseConnection as error:
            error.request_id = command.id
            raise
        if response is not None:
            if command.id is not None:
                response["id"] = command.id
            connection.publish(response)


async def _execute(connection: PanelConnection, command: ClientMessage) -> Message | None:
    match command.type:
        case "auth" | "auth.refresh":
            return await connection.authenticate(command.token, refresh=command.type == "auth.refresh")
        case "ping":
            return connection.ping()
        case "subscribe" | "unsubscribe":
            if command.meeting_id is None:
                raise CloseConnection(4400)
            if command.type == "subscribe":
                return await connection.subscribe(command.meeting_id)
            connection.unsubscribe(command.meeting_id)
            return None


async def _write(websocket: WebSocket, connection: PanelConnection) -> None:
    loop = asyncio.get_running_loop()
    next_batch = loop.time() + _BATCH_SECONDS
    while True:
        connection.tick()
        message = None
        if loop.time() >= next_batch and connection.output.empty():
            message = connection.next_batch()
            next_batch = loop.time() + _BATCH_SECONDS
        if message is None:
            try:
                async with asyncio.timeout(max(next_batch - loop.time(), 0)):
                    message = await connection.output.get()
            except TimeoutError:
                continue
        try:
            async with asyncio.timeout(2):
                await websocket.send_json(message)
        except TimeoutError as error:
            raise CloseConnection(1013) from error
