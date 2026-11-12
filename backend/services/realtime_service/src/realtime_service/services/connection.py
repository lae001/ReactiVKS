"""Сценарии соединения с панелью организатора."""

from asyncio import Queue, QueueFull
from collections import OrderedDict
from datetime import timedelta
from uuid import UUID

from realtime_service.domain.meeting import MeetingReader
from realtime_service.services.live_rooms import LiveRoom, LiveRooms, Message, Subscription
from vks_common.auth import InvalidToken, TokenVerifier
from vks_common.auth.claims import AuthenticatedUser
from vks_common.clock import Clock


class CloseConnection(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        self.request_id: str | int | None = None


class PanelConnection:
    def __init__(self, *, clock: Clock, verifier: TokenVerifier, meetings: MeetingReader, rooms: LiveRooms) -> None:
        self._clock = clock
        self._verifier = verifier
        self._meetings = meetings
        self._rooms = rooms
        self._user: AuthenticatedUser | None = None
        self._subscriptions: OrderedDict[UUID, tuple[LiveRoom, Subscription]] = OrderedDict()
        self._handshake_done = False
        self._connected_at = clock.now()
        self._last_ping = self._connected_at
        self.output: Queue[Message] = Queue(maxsize=128)

    @property
    def is_authenticated(self) -> bool:
        return self._user is not None

    async def authenticate(self, token: str | None, *, refresh: bool) -> Message:
        if token is None or (self._user is not None) != refresh:
            raise CloseConnection(4400)
        try:
            caller = await self._verifier.verify(token)
        except InvalidToken as error:
            raise CloseConnection(4401) from error
        if caller.expires_at <= self._clock.now():
            raise CloseConnection(4401)
        if self._user is not None and self._user.user_id != caller.user_id:
            raise CloseConnection(4403)
        self._user = caller
        return {"type": "welcome", "user_id": str(caller.user_id), "server_time": self._clock.now().isoformat()}

    async def subscribe(self, meeting_id: UUID) -> Message:
        if self._user is None:
            raise CloseConnection(4401)
        owner_id = self._user.user_id
        if not await self._meetings.is_allowed(meeting_id, owner_id):
            raise CloseConnection(4403)

        room = self._rooms.reserve(meeting_id)
        try:
            if room.owner_id is None:
                snapshot = await self._meetings.snapshot(meeting_id)
                if snapshot is None or snapshot.owner_id != owner_id:
                    raise CloseConnection(4403)
                room.initialize(snapshot)
            if room.is_deleted or room.owner_id != owner_id:
                raise CloseConnection(4403)

            if meeting_id not in self._subscriptions:
                subscription = Subscription(self.output)
                subscription.delivered = {
                    participant_id: participant.last
                    for participant_id, participant in room.participants.items()
                    if participant.last is not None
                }
                self._subscriptions[meeting_id] = (room, subscription)
                room.subscriptions.add(subscription)
            _, subscription = self._subscriptions[meeting_id]
            now = self._clock.now()
            subscription.analysis = room.analysis(now)
            self._handshake_done = True
            return room.message("subscribed", snapshot=room.snapshot(now))
        finally:
            self._rooms.release(room)

    def unsubscribe(self, meeting_id: UUID) -> None:
        current = self._subscriptions.pop(meeting_id, None)
        if current is not None:
            room, subscription = current
            room.subscriptions.remove(subscription)
            self._rooms.prune(room)

    def ping(self) -> Message:
        self._last_ping = self._clock.now()
        return {"type": "pong", "server_time": self._last_ping.isoformat()}

    def publish(self, message: Message) -> None:
        try:
            self.output.put_nowait(message)
        except QueueFull as error:
            raise CloseConnection(1013) from error

    def tick(self) -> None:
        now = self._clock.now()
        if not self._handshake_done and now - self._connected_at >= timedelta(seconds=10):
            raise CloseConnection(4408)
        if self._user is not None and now >= self._user.expires_at + timedelta(seconds=60):
            raise CloseConnection(4401)
        if now - self._last_ping >= timedelta(seconds=60):
            raise CloseConnection(4408)
        for room, subscription in self._subscriptions.values():
            if subscription.close_code is not None:
                raise CloseConnection(subscription.close_code)
            analysis = room.analysis(now)
            if analysis != subscription.analysis:
                self.publish(room.message("analysis.status", **analysis))
                subscription.analysis = analysis

    def next_batch(self) -> Message | None:
        for meeting_id, (room, subscription) in self._subscriptions.items():
            message = room.batch(subscription)
            if message is not None:
                # При нескольких подписках встречи получают очередность в пределах общего лимита соединения.
                self._subscriptions.move_to_end(meeting_id)
                return message
        return None

    def close(self) -> None:
        for meeting_id in list(self._subscriptions):
            self.unsubscribe(meeting_id)
