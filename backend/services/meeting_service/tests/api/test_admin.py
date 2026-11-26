"""Администратор видит все встречи, организатор не получает административный доступ."""

import httpx
import pytest

from vks_common.testing import TokenFactory

pytestmark = pytest.mark.integration


async def test_admin_meetings_roles_and_cursor(client: httpx.AsyncClient, tokens: TokenFactory) -> None:
    organizer = {"Authorization": "Bearer " + tokens.issue()}
    admin = {"Authorization": "Bearer " + tokens.issue(role="admin")}
    for title in ("Первая", "Вторая"):
        assert (await client.post("/api/v1/meetings", headers=organizer, json={"title": title})).status_code == 201
    assert (await client.get("/api/v1/admin/meetings", headers=organizer)).status_code == 403
    assert (await client.get("/api/v1/admin/health", headers=organizer)).status_code == 403
    first = await client.get("/api/v1/admin/meetings?limit=1", headers=admin)
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 1 and page["items"][0]["online_participants"] == 0
    second = await client.get("/api/v1/admin/meetings", params={"cursor": page["next_cursor"]}, headers=admin)
    assert second.json()["items"][0]["id"] != page["items"][0]["id"]
    assert (await client.get("/api/v1/admin/meetings?cursor=invalid", headers=admin)).status_code == 422
    assert (await client.get("/api/v1/admin/meetings?status=active", headers=admin)).json()["items"] == []
