from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from vks_common.clock import FixedClock, SystemClock
from vks_common.ids import new_id, new_token


def test_system_clock_is_aware_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_fixed_clock_moves_only_when_advanced() -> None:
    moment = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    clock = FixedClock(moment)

    clock.advance(timedelta(minutes=15))

    assert clock.now() == moment + timedelta(minutes=15)


def test_fixed_clock_refuses_naive_moment() -> None:
    with pytest.raises(ValueError, match="часовым поясом"):
        FixedClock(datetime(2026, 10, 12, 9, 0))  # noqa: DTZ001 - проверяется именно наивный момент


def test_new_id_is_version_7_and_grows() -> None:
    first, second = new_id(), new_id()

    assert type(first) is UUID
    assert first.version == 7
    assert second > first


def test_new_token_has_256_bits_by_default() -> None:
    token = new_token()

    # 32 байта в base64url без выравнивания – 43 символа.
    assert len(token) == 43
    assert new_token() != token
