from datetime import UTC, datetime
from uuid import uuid4

import pytest

from meeting_service.domain.consent import (
    ConsentDecision,
    ConsentNotice,
    check_notice_version,
    decide_consent,
)
from meeting_service.domain.errors import ConsentRequired, InvalidDisplayName, NoticeOutdated
from meeting_service.domain.identifiers import MeetingId, ParticipantId, UserId
from meeting_service.domain.livekit import room_access
from meeting_service.domain.meetings import Meeting, Organizer
from meeting_service.domain.participants import (
    ConsentState,
    Participant,
    ParticipantRole,
    hash_participant_token,
    normalize_display_name,
)

NOTICE = ConsentNotice(version="v1", text_md="…")
NOW = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)


def test_consent_is_not_asked_when_analysis_is_off() -> None:
    assert decide_consent(analysis_enabled=False, decision=None) is ConsentState.NOT_REQUIRED
    assert decide_consent(analysis_enabled=False, decision=ConsentDecision.GRANTED) is ConsentState.NOT_REQUIRED


def test_silence_is_not_consent() -> None:
    with pytest.raises(ConsentRequired):
        decide_consent(analysis_enabled=True, decision=None)


@pytest.mark.parametrize("decision", list(ConsentDecision))
def test_decision_becomes_consent_state(decision: ConsentDecision) -> None:
    assert decide_consent(analysis_enabled=True, decision=decision).value == decision.value


def test_decision_must_be_about_current_notice() -> None:
    check_notice_version("v1", notice=NOTICE)

    with pytest.raises(NoticeOutdated):
        check_notice_version("v0", notice=NOTICE)
    with pytest.raises(ConsentRequired):
        check_notice_version(None, notice=NOTICE)


@pytest.mark.parametrize("raw", ["", "  ", "x" * 65])
def test_display_name_is_1_to_64_characters(raw: str) -> None:
    with pytest.raises(InvalidDisplayName):
        normalize_display_name(raw)


def test_participant_token_is_hashed_with_sha256() -> None:
    token_hash = hash_participant_token("pt_secret")

    assert len(token_hash) == 32
    assert token_hash == hash_participant_token("pt_secret")
    assert token_hash != hash_participant_token("pt_other")


def test_room_access_carries_role_and_consent_as_attributes() -> None:
    meeting = Meeting.schedule(
        meeting_id=MeetingId(uuid4()),
        organizer=Organizer(user_id=UserId(uuid4()), name="Иван"),
        title="Планерка",
        invite_code="k3m7qx4tpa",
        scheduled_at=None,
        analysis_enabled=True,
        analysis_fps=3,
        now=NOW,
    )
    guest = Participant(
        id=ParticipantId(uuid4()),
        meeting_id=meeting.id,
        display_name="Анна",
        role=ParticipantRole.GUEST,
        consent_state=ConsentState.DENIED,
        created_at=NOW,
    )

    access = room_access(meeting, guest)

    assert access.room == str(meeting.id)
    assert access.identity == f"p_{guest.id}"
    assert dict(access.attributes) == {"vks.role": "guest", "vks.consent": "denied", "vks.kind": "human"}
