"""Схема ``/api/v1/settings`` – настройки анализа для новых встреч организатора."""

from __future__ import annotations

from pydantic import BaseModel, Field

from meeting_service.domain.meetings import MAX_ANALYSIS_FPS, MIN_ANALYSIS_FPS, AnalysisDefaults

__all__ = ["OrganizerSettingsBody"]


class OrganizerSettingsBody(BaseModel):
    """``Settings`` контракта – и запрос ``PUT``, и ответ."""

    analysis_enabled_default: bool
    analysis_fps_default: int = Field(ge=MIN_ANALYSIS_FPS, le=MAX_ANALYSIS_FPS)

    @classmethod
    def from_domain(cls, defaults: AnalysisDefaults) -> OrganizerSettingsBody:
        return cls(analysis_enabled_default=defaults.enabled, analysis_fps_default=defaults.fps)
