"""Эндпоинты ``/api/v1/settings`` – настройки анализа по умолчанию для новых встреч организатора (Bearer)."""

from __future__ import annotations

from fastapi import APIRouter, status

from meeting_service.api.v1.dependencies import (
    CallingOrganizer,
    GetOrganizerSettingsScenario,
    SaveOrganizerSettingsScenario,
)
from meeting_service.schemas.organizer_settings import OrganizerSettingsBody

__all__ = ["router"]

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Нет access-токена или он недействителен"}},
)


@router.get("", summary="Настройки анализа по умолчанию")
async def read_settings(organizer: CallingOrganizer, scenario: GetOrganizerSettingsScenario) -> OrganizerSettingsBody:
    """Организатор их не менял – анализ включен, 3 кадра в секунду."""
    defaults = await scenario.execute(owner_id=organizer.user_id)
    return OrganizerSettingsBody.from_domain(defaults)


@router.put(
    "",
    summary="Сохранить настройки анализа по умолчанию",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Частота анализа вне 2–5"}},
)
async def save_settings(
    body: OrganizerSettingsBody, organizer: CallingOrganizer, scenario: SaveOrganizerSettingsScenario
) -> OrganizerSettingsBody:
    """Действуют для встреч, созданных после сохранения, – если при создании параметры анализа не указаны."""
    defaults = await scenario.execute(
        owner_id=organizer.user_id,
        analysis_enabled=body.analysis_enabled_default,
        analysis_fps=body.analysis_fps_default,
    )
    return OrganizerSettingsBody.from_domain(defaults)
