"""Heartbeat активных ML-заданий: устаревшее событие не восстанавливает статус."""

from datetime import datetime

from vks_contracts import ParsedEvent
from vks_contracts.ml_events import MlStatus


class MlHeartbeat:
    def __init__(self) -> None:
        self.latest: datetime | None = None

    async def execute(self, event: ParsedEvent) -> None:
        if isinstance(event.payload, MlStatus) and event.payload.state == "active":
            at = event.envelope.occurred_at
            if self.latest is None or at > self.latest:
                self.latest = at
