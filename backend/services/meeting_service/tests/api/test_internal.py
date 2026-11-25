"""Внутренний API встреч доступен только сервисам с общим секретом."""

from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from meeting_service.settings import MeetingSettings

pytestmark = pytest.mark.integration
SERVICE_TOKEN = "test-internal-0123456789abcdef0123456789"  # noqa: S105


@pytest.fixture
def settings(settings: MeetingSettings) -> MeetingSettings:
    return settings.model_copy(update={"service_token": SecretStr(SERVICE_TOKEN)})


async def test_internal_snapshot_requires_service_token(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/internal/meetings/{uuid4()}")

    assert response.status_code == 401


async def test_returns_snapshot_and_checks_ownership(
    client: httpx.AsyncClient, organizer_headers: Callable[..., dict[str, str]]
) -> None:
    owner = uuid4()
    headers = organizer_headers(owner)
    created = await client.post("/api/v1/meetings", headers=headers, json={"title": "Демонстрация"})
    meeting_id = created.json()["id"]
    joined = await client.post(f"/api/v1/meetings/{meeting_id}/join", headers=headers, json={"consent": "granted"})
    service = {"X-Service-Token": SERVICE_TOKEN}
    path = f"/internal/meetings/{meeting_id}"

    response = await client.get(path, headers=service)
    access = await client.get(f"{path}/access", headers=service, params={"user_id": str(owner)})
    refused = await client.get(f"{path}/access", headers=service, params={"user_id": str(uuid4())})

    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["owner_id"] == str(owner)
    assert snapshot["participants"][0]["id"] == joined.json()["participant_id"]
    assert snapshot["participants"][0]["consent_state"] == "granted"
    assert access.json() == {"allowed": True, "meeting_status": "active", "analysis_enabled": True}
    assert refused.json()["allowed"] is False
