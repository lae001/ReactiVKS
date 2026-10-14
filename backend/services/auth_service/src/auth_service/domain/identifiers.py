"""Идентификаторы auth-service: разные типы, чтобы перепутанные UUID ловил mypy."""

from typing import NewType
from uuid import UUID

__all__ = ["RefreshTokenId", "SessionFamilyId", "UserId"]

UserId = NewType("UserId", UUID)
RefreshTokenId = NewType("RefreshTokenId", UUID)
# Семья refresh-токенов – цепочка ротаций одного входа (одного устройства).
SessionFamilyId = NewType("SessionFamilyId", UUID)
