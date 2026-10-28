"""Таблица ``auth.outbox`` – общее определение шасси (vks_common.kafka) в схеме сервиса."""

from auth_service.models.base import Base
from vks_common.kafka import outbox_table

__all__ = ["OUTBOX"]

OUTBOX = outbox_table(Base.metadata)
