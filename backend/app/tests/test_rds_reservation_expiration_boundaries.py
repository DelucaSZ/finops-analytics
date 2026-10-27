from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import rds_reservation_opportunities as opportunities

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (29, True),
        (30, True),
        (31, False),
    ],
)
def test_expiring_within_30_days_boundary(days: int, expected: bool) -> None:
    reservation = SimpleNamespace(
        is_active=True,
        state="active",
        start_time=NOW - timedelta(days=100),
        expiration_at=NOW + timedelta(days=days),
    )

    assert settings.rds_reservation_expiration_warning_days == 30
    delta = opportunities._expiration_delta(reservation, now=NOW)
    within_warning_window = opportunities._active_for_expiration(
        reservation, now=NOW
    ) and timedelta(0) <= delta <= timedelta(days=settings.rds_reservation_expiration_warning_days)

    assert opportunities._days_until_expiration(reservation, now=NOW) == days
    assert within_warning_window is expected
