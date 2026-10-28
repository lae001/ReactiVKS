"""Присутствие участника в комнате, предел встречи и сопоставление комнаты и identity LiveKit."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from meeting_service.domain.errors import MeetingFull
from meeting_service.domain.identifiers import MeetingId, ParticipantId
from meeting_service.domain.livekit import meeting_id_of_room, participant_id_of_identity
from meeting_service.domain.participants import (
    MAX_MEETING_PARTICIPANTS,
    ConsentState,
    Participant,
    ParticipantRole,
    ensure_seat_available,
)

NOW = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def make_participant(**overrides: object) -> Participant:
    fields: dict[str, object] = {
        "id": ParticipantId(uuid4()),
        "meeting_id": MeetingId(uuid4()),
        "display_name": "Анна",
        "role": ParticipantRole.GUEST,
        "consent_state": ConsentState.GRANTED,
        "created_at": NOW,
    } | overrides
    return Participant(**fields)  # type: ignore[arg-type]  # поля задаются тестом по имени


@pytest.mark.parametrize(
    ("joined", "left", "is_online"),
    [
        pytest.param(None, None, False, id="never-joined"),
        pytest.param(NOW, None, True, id="joined"),
        pytest.param(NOW, LATER, False, id="left"),
        pytest.param(LATER, NOW, True, id="rejoined"),
        pytest.param(NOW, NOW, False, id="left-in-same-second"),
    ],
)
def test_participant_is_online_when_last_join_is_after_last_leave(
    joined: datetime | None, left: datetime | None, is_online: bool
) -> None:
    participant = make_participant(last_joined_at=joined, last_left_at=left)

    assert participant.is_online is is_online


def test_removed_participant_is_not_online() -> None:
    assert make_participant(last_joined_at=NOW, is_removed=True).is_online is False


def test_tenth_participant_still_gets_a_seat() -> None:
    ensure_seat_available(MAX_MEETING_PARTICIPANTS - 1)


def test_eleventh_participant_is_refused() -> None:
    with pytest.raises(MeetingFull):
        ensure_seat_available(MAX_MEETING_PARTICIPANTS)


def test_identity_and_room_map_back_to_participant_and_meeting() -> None:
    participant_id, meeting_id = uuid4(), uuid4()

    assert participant_id_of_identity(f"p_{participant_id}") == participant_id
    assert meeting_id_of_room(str(meeting_id)) == meeting_id


@pytest.mark.parametrize("identity", [None, "", "agent-0192", "p_not-a-uuid", str(uuid4())])
def test_foreign_identities_are_not_participants(identity: str | None) -> None:
    assert participant_id_of_identity(identity) is None


def test_foreign_room_is_not_a_meeting() -> None:
    assert meeting_id_of_room("lobby-test") is None
