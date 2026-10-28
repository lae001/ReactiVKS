"""Идентификаторы meeting-service: разные типы, чтобы перепутанные UUID ловил mypy."""

from typing import NewType
from uuid import UUID

__all__ = ["MeetingId", "ParticipantId", "UserId"]

MeetingId = NewType("MeetingId", UUID)
ParticipantId = NewType("ParticipantId", UUID)
# Учетная запись организатора – sub access-токена; сама запись живет в auth-service.
UserId = NewType("UserId", UUID)
