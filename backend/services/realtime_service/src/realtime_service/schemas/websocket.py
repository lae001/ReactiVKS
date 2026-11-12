"""Входящие команды протокола vks.v1."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

type RequestId = str | int


class ClientMessage(BaseModel):
    type: Literal["auth", "auth.refresh", "subscribe", "unsubscribe", "ping"]
    id: RequestId | None = None
    token: str | None = Field(default=None, min_length=1)
    meeting_id: UUID | None = None
