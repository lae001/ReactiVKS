"""Настройки анализа по умолчанию: ``/api/v1/settings`` (EMO-68)."""

from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.integration

SETTINGS = "/api/v1/settings"

OrganizerHeaders = Callable[..., dict[str, str]]


async def test_settings_default_to_analysis_at_3_fps(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    response = await client.get(SETTINGS, headers=organizer_headers())

    assert response.status_code == 200
    assert response.json() == {"analysis_enabled_default": True, "analysis_fps_default": 3}


async def test_saved_settings_apply_to_new_meetings(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    headers = organizer_headers(uuid4())
    body = {"analysis_enabled_default": False, "analysis_fps_default": 5}

    saved = await client.put(SETTINGS, json=body, headers=headers)
    meeting = (await client.post("/api/v1/meetings", json={"title": "Планерка"}, headers=headers)).json()

    assert saved.status_code == 200
    assert saved.json() == body
    assert (await client.get(SETTINGS, headers=headers)).json() == body
    assert (meeting["analysis_enabled"], meeting["analysis_fps"]) == (False, 5)


async def test_settings_are_saved_again_over_previous(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    headers = organizer_headers(uuid4())
    await client.put(SETTINGS, json={"analysis_enabled_default": False, "analysis_fps_default": 5}, headers=headers)

    await client.put(SETTINGS, json={"analysis_enabled_default": True, "analysis_fps_default": 2}, headers=headers)

    assert (await client.get(SETTINGS, headers=headers)).json() == {
        "analysis_enabled_default": True,
        "analysis_fps_default": 2,
    }


async def test_settings_belong_to_their_organizer(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    await client.put(
        SETTINGS, json={"analysis_enabled_default": False, "analysis_fps_default": 5}, headers=organizer_headers()
    )

    response = await client.get(SETTINGS, headers=organizer_headers())

    assert response.json() == {"analysis_enabled_default": True, "analysis_fps_default": 3}


@pytest.mark.parametrize(
    ("body", "field"),
    [
        pytest.param({"analysis_enabled_default": True, "analysis_fps_default": 6}, "analysis_fps_default", id="fps"),
        pytest.param({"analysis_fps_default": 3}, "analysis_enabled_default", id="missing-flag"),
    ],
)
async def test_invalid_settings_are_422(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, body: dict[str, object], field: str
) -> None:
    response = await client.put(SETTINGS, json=body, headers=organizer_headers())

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", field]


async def test_settings_require_access_token(client: httpx.AsyncClient) -> None:
    read = await client.get(SETTINGS)
    saved = await client.put(SETTINGS, json={"analysis_enabled_default": True, "analysis_fps_default": 3})

    assert (read.status_code, saved.status_code) == (401, 401)
