"""Настройки организатора: параметры анализа, которые получает новая встреча (функция 6.10)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from meeting_service.domain.identifiers import UserId
from meeting_service.domain.meetings import AnalysisDefaults, check_analysis_fps
from meeting_service.repositories.organizer_settings import OrganizerSettingsRepository
from vks_common.clock import Clock
from vks_common.db import transaction

__all__ = ["GetOrganizerSettings", "SaveOrganizerSettings"]


class GetOrganizerSettings:
    """Настройки организатора; он их не менял – значения по умолчанию."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._settings = OrganizerSettingsRepository(session)

    async def execute(self, *, owner_id: UserId) -> AnalysisDefaults:
        async with transaction(self._session):
            return await self._settings.get_defaults(owner_id)


class SaveOrganizerSettings:
    """Сохранить настройки целиком (``PUT``). На уже созданные встречи они не влияют."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._settings = OrganizerSettingsRepository(session)
        self._clock = clock

    async def execute(self, *, owner_id: UserId, analysis_enabled: bool, analysis_fps: int) -> AnalysisDefaults:
        defaults = AnalysisDefaults(enabled=analysis_enabled, fps=check_analysis_fps(analysis_fps))
        async with transaction(self._session):
            await self._settings.save_defaults(owner_id, defaults, now=self._clock.now())
        return defaults
