from collections.abc import Callable
from uuid import UUID, uuid4

import httpx
import pytest

pytestmark = pytest.mark.integration

MEETINGS = "/api/v1/meetings"

OrganizerHeaders = Callable[..., dict[str, str]]


async def create(client: httpx.AsyncClient, headers: dict[str, str], **body: object) -> dict[str, object]:
    response = await client.post(MEETINGS, json={"title": "Планерка"} | body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


async def test_create_meeting_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.post(MEETINGS, json={"title": "Планерка"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_created_meeting_is_scheduled_with_invite_link(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    response = await client.post(
        MEETINGS,
        json={"title": "  Переговоры с ООО «Ромашка» ", "scheduled_at": "2026-11-20T07:00:00Z"},
        headers=organizer_headers(),
    )

    assert response.status_code == 201
    meeting = response.json()
    assert meeting["title"] == "Переговоры с ООО «Ромашка»"
    assert meeting["status"] == "scheduled"
    assert meeting["scheduled_at"] == "2026-11-20T07:00:00Z"
    assert meeting["invite_url"] == f"https://vks.example.ru/j/{meeting['invite_code']}"
    assert len(meeting["invite_code"]) == 10
    assert meeting["participants_count"] == 0


async def test_analysis_defaults_to_enabled_at_3_fps(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    meeting = await create(client, organizer_headers())

    assert (meeting["analysis_enabled"], meeting["analysis_fps"]) == (True, 3)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        pytest.param({"title": ""}, "title", id="empty-title"),
        pytest.param({"title": "   "}, "title", id="blank-title"),
        pytest.param({"title": "x" * 201}, "title", id="long-title"),
        pytest.param({"title": "Планерка", "analysis_fps": 6}, "analysis_fps", id="fps-too-high"),
        pytest.param({"title": "Планерка", "scheduled_at": "2026-11-20T07:00:00"}, "scheduled_at", id="naive-time"),
    ],
)
async def test_invalid_meeting_is_422(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, body: dict[str, object], field: str
) -> None:
    response = await client.post(MEETINGS, json=body, headers=organizer_headers())

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", field]


async def test_meeting_card_of_owner(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    owner = uuid4()
    meeting = await create(client, organizer_headers(owner))

    response = await client.get(f"{MEETINGS}/{meeting['id']}", headers=organizer_headers(owner))

    assert response.status_code == 200
    assert response.json() == meeting


async def test_foreign_meeting_is_404(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    meeting = await create(client, organizer_headers())

    response = await client.get(f"{MEETINGS}/{meeting['id']}", headers=organizer_headers())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_list_contains_only_own_meetings_newest_first(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    owner = uuid4()
    await create(client, organizer_headers(owner), title="Ранняя", scheduled_at="2026-11-21T07:00:00Z")
    await create(client, organizer_headers(owner), title="Поздняя", scheduled_at="2026-11-22T07:00:00Z")
    await create(client, organizer_headers(), title="Чужая")

    response = await client.get(MEETINGS, headers=organizer_headers(owner))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Поздняя", "Ранняя"]
    assert response.json()["next_cursor"] is None


async def test_list_is_paginated_by_cursor(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    owner = uuid4()
    for day in range(21, 26):
        await create(client, organizer_headers(owner), title=f"Встреча {day}", scheduled_at=f"2026-11-{day}T07:00:00Z")

    first = (await client.get(MEETINGS, params={"limit": 2}, headers=organizer_headers(owner))).json()
    second = (
        await client.get(
            MEETINGS, params={"limit": 2, "cursor": first["next_cursor"]}, headers=organizer_headers(owner)
        )
    ).json()
    third = (
        await client.get(
            MEETINGS, params={"limit": 2, "cursor": second["next_cursor"]}, headers=organizer_headers(owner)
        )
    ).json()

    titles = [item["title"] for page in (first, second, third) for item in page["items"]]
    assert titles == ["Встреча 25", "Встреча 24", "Встреча 23", "Встреча 22", "Встреча 21"]
    assert third["next_cursor"] is None


async def test_list_is_filtered_by_title_and_dates(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    owner = uuid4()
    await create(client, organizer_headers(owner), title="Планерка 100%", scheduled_at="2026-11-21T07:00:00Z")
    await create(client, organizer_headers(owner), title="Планерка 50", scheduled_at="2026-11-25T07:00:00Z")
    await create(client, organizer_headers(owner), title="Ретро", scheduled_at="2026-11-21T09:00:00Z")

    by_text = await client.get(MEETINGS, params={"q": "100%"}, headers=organizer_headers(owner))
    by_dates = await client.get(
        MEETINGS, params={"from": "2026-11-21", "to": "2026-11-21"}, headers=organizer_headers(owner)
    )

    assert [item["title"] for item in by_text.json()["items"]] == ["Планерка 100%"]
    assert {item["title"] for item in by_dates.json()["items"]} == {"Планерка 100%", "Ретро"}


@pytest.mark.parametrize(
    ("params", "loc"),
    [
        pytest.param({"status": "paused"}, ["query", "status"], id="unknown-status"),
        pytest.param({"cursor": "not-a-cursor"}, ["query", "cursor"], id="foreign-cursor"),
        pytest.param({"limit": 0}, ["query", "limit"], id="zero-limit"),
    ],
)
async def test_invalid_list_query_is_422(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders, params: dict[str, str | int], loc: list[str]
) -> None:
    response = await client.get(MEETINGS, params=params, headers=organizer_headers())

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == loc


async def test_list_requires_access_token(client: httpx.AsyncClient) -> None:
    response = await client.get(MEETINGS)

    assert response.status_code == 401


async def test_end_requires_meeting_to_have_started(
    client: httpx.AsyncClient, organizer_headers: OrganizerHeaders
) -> None:
    owner = uuid4()
    meeting = await create(client, organizer_headers(owner))

    response = await client.post(f"{MEETINGS}/{meeting['id']}/end", headers=organizer_headers(owner))

    assert response.status_code == 409
    assert response.json()["code"] == "meeting_not_started"


async def test_end_of_foreign_meeting_is_404(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    meeting = await create(client, organizer_headers())

    response = await client.post(f"{MEETINGS}/{meeting['id']}/end", headers=organizer_headers())

    assert response.status_code == 404


async def test_unknown_meeting_id_is_404(client: httpx.AsyncClient, organizer_headers: OrganizerHeaders) -> None:
    response = await client.get(f"{MEETINGS}/{UUID(int=0)}", headers=organizer_headers())

    assert response.status_code == 404
