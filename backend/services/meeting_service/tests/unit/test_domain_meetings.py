from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from meeting_service.domain.errors import (
    InvalidAnalysisFps,
    InvalidTitle,
    MeetingCancelled,
    MeetingEnded,
    MeetingNotStarted,
)
from meeting_service.domain.identifiers import MeetingId, UserId
from meeting_service.domain.meetings import (
    EndReason,
    InvalidCursor,
    Meeting,
    MeetingCursor,
    MeetingStatus,
    Organizer,
    invite_code_from,
    is_invite_code,
)

NOW = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)


def make_meeting(**overrides: object) -> Meeting:
    meeting = Meeting.schedule(
        meeting_id=MeetingId(uuid4()),
        organizer=Organizer(user_id=UserId(uuid4()), name="Иван Петров"),
        title="Планерка",
        invite_code="k3m7qx4tpa",
        scheduled_at=None,
        analysis_enabled=True,
        analysis_fps=3,
        now=NOW,
    )
    fields = {name: getattr(meeting, name) for name in meeting.__dataclass_fields__} | overrides
    return Meeting(**fields)


def test_new_meeting_is_scheduled_with_trimmed_title() -> None:
    meeting = make_meeting(title="Планерка")

    assert meeting.status is MeetingStatus.SCHEDULED
    assert meeting.started_at is None


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_title_must_be_1_to_200_characters(title: str) -> None:
    with pytest.raises(InvalidTitle):
        Meeting.schedule(
            meeting_id=MeetingId(uuid4()),
            organizer=Organizer(user_id=UserId(uuid4()), name="Иван"),
            title=title,
            invite_code="k3m7qx4tpa",
            scheduled_at=None,
            analysis_enabled=True,
            analysis_fps=3,
            now=NOW,
        )


@pytest.mark.parametrize("fps", [1, 6])
def test_analysis_rate_is_2_to_5_fps(fps: int) -> None:
    with pytest.raises(InvalidAnalysisFps):
        Meeting.schedule(
            meeting_id=MeetingId(uuid4()),
            organizer=Organizer(user_id=UserId(uuid4()), name="Иван"),
            title="Планерка",
            invite_code="k3m7qx4tpa",
            scheduled_at=None,
            analysis_enabled=True,
            analysis_fps=fps,
            now=NOW,
        )


def test_first_organizer_entry_starts_meeting() -> None:
    started = make_meeting().started(NOW)

    assert started.status is MeetingStatus.ACTIVE
    assert started.started_at == NOW


def test_repeated_organizer_entry_changes_nothing() -> None:
    active = make_meeting().started(NOW)

    assert active.started(NOW + timedelta(minutes=5)) is active


@pytest.mark.parametrize(
    ("status", "error"),
    [(MeetingStatus.ENDED, MeetingEnded), (MeetingStatus.CANCELLED, MeetingCancelled)],
)
def test_closed_meeting_cannot_be_entered(status: MeetingStatus, error: type[Exception]) -> None:
    meeting = make_meeting(status=status, started_at=NOW, ended_at=NOW)

    with pytest.raises(error):
        meeting.started(NOW)
    with pytest.raises(error):
        meeting.ensure_open_for_guests()


def test_guest_waits_for_organizer() -> None:
    with pytest.raises(MeetingNotStarted):
        make_meeting().ensure_open_for_guests()


def test_ending_is_idempotent() -> None:
    ended = make_meeting().started(NOW).ended(NOW + timedelta(hours=1), EndReason.ORGANIZER)

    assert ended.status is MeetingStatus.ENDED
    assert ended.end_reason is EndReason.ORGANIZER
    assert ended.ended(NOW + timedelta(hours=2), EndReason.ORGANIZER) is ended


def test_meeting_that_never_started_cannot_be_ended() -> None:
    with pytest.raises(MeetingNotStarted):
        make_meeting().ended(NOW, EndReason.ORGANIZER)


def test_cancelled_meeting_cannot_be_ended() -> None:
    with pytest.raises(MeetingCancelled):
        make_meeting(status=MeetingStatus.CANCELLED).ended(NOW, EndReason.ORGANIZER)


def test_invite_code_is_10_lowercase_base32_characters() -> None:
    code = invite_code_from(bytes(range(7)))

    assert len(code) == 10
    assert is_invite_code(code)


def test_invite_code_needs_enough_entropy() -> None:
    with pytest.raises(ValueError, match="случайных байт"):
        invite_code_from(b"short")


@pytest.mark.parametrize("value", ["K3M7QX4TPA", "k3m7qx4tp1", "k3m7qx4tp", "k3m7qx4tpaa", ""])
def test_strings_that_are_not_invite_codes(value: str) -> None:
    assert not is_invite_code(value)


def test_cursor_survives_round_trip() -> None:
    cursor = MeetingCursor(sort_key=NOW, meeting_id=uuid4())

    assert MeetingCursor.decode(cursor.encode()) == cursor


@pytest.mark.parametrize(
    "value", ["", "not-a-cursor", "eyJrIjoxfQ", "eyJrIjoiMjAyNi0xMS0yMFQwNzowMDowMCIsImlkIjoieCJ9"]
)
def test_foreign_cursor_is_refused(value: str) -> None:
    with pytest.raises(InvalidCursor):
        MeetingCursor.decode(value)
