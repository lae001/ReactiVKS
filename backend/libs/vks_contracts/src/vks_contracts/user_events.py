"""Топик ``user.events`` – производитель auth-service (через outbox), ключ – ``user_id``."""

from __future__ import annotations

from vks_contracts.envelope import UserKeyed
from vks_contracts.topics import Topic

__all__ = ["UserBlocked", "UserDeleted", "UserUnblocked"]


class _UserEvent(UserKeyed):
    topic = Topic.USER_EVENTS


class UserBlocked(_UserEvent):
    event_type = "user.blocked"


class UserUnblocked(_UserEvent):
    event_type = "user.unblocked"


class UserDeleted(_UserEvent):
    """meeting-service удаляет встречи пользователя (с публикацией ``meeting.deleted``)."""

    event_type = "user.deleted"
