"""Настройки организатора: ``meeting.organizer_settings``."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import UserId
from meeting_service.domain.meetings import AnalysisDefaults
from meeting_service.models import OrganizerSettingsRow

__all__ = ["OrganizerSettingsRepository"]


class OrganizerSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_defaults(self, user_id: UserId) -> AnalysisDefaults:
        """Настройки анализа для новых встреч; организатор их не менял – значения по умолчанию."""
        row = await self._session.get(OrganizerSettingsRow, user_id)
        if row is None:
            return AnalysisDefaults()
        return AnalysisDefaults(enabled=row.analysis_enabled_default, fps=row.analysis_fps_default)
