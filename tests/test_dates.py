from datetime import UTC, date, datetime

import pytest

from timemachine import dates
from timemachine.dates import date_path_parts, now_utc_iso, snapshot_date


@pytest.mark.parametrize(
    ("utc_now", "expected"),
    [
        # Evening runs keep their own date, in EST and in EDT.
        ("2026-11-04T04:11:00", date(2026, 11, 3)),  # Tue 23:11 EST
        ("2026-10-07T03:34:00", date(2026, 10, 6)),  # Tue 23:34 EDT
        # Runs GitHub delayed past midnight ET belong to the evening they missed
        # (the real 2026-10-06 and 2026-10-13 runs).
        ("2026-10-06T04:06:00", date(2026, 10, 5)),  # 00:06 EDT
        ("2026-10-13T04:48:00", date(2026, 10, 12)),  # 00:48 EDT
        # Later delays, and same-morning reruns, up to the cutoff.
        ("2026-08-28T08:15:00", date(2026, 8, 27)),  # 04:15 EDT
        ("2026-11-04T14:59:00", date(2026, 11, 3)),  # 09:59 EST
        ("2026-10-06T13:59:00", date(2026, 10, 5)),  # 09:59 EDT
        # From the cutoff on, a run belongs to the current day.
        ("2026-11-04T15:00:00", date(2026, 11, 4)),  # 10:00 EST
        ("2026-10-06T14:00:00", date(2026, 10, 6)),  # 10:00 EDT
        # Month and year boundaries.
        ("2027-01-01T13:00:00", date(2026, 12, 31)),  # 08:00 EST
    ],
)
def test_snapshot_date_treats_runs_before_cutoff_as_previous_day(
    monkeypatch, utc_now: str, expected: date
):
    now = datetime.fromisoformat(utc_now).replace(tzinfo=UTC)
    monkeypatch.setattr(dates, "now_utc", lambda: now)

    assert snapshot_date() == expected


def test_now_utc_iso_ends_with_z():
    s = now_utc_iso()
    assert s.endswith("Z")
    assert "T" in s
    # No timezone offset in the body; trailing Z replaces +00:00.
    assert "+" not in s


def test_date_path_parts():
    year, full = date_path_parts(date(2026, 5, 14))
    assert year == "2026"
    assert full == "2026-05-14"


def test_date_path_parts_pads_single_digit_months():
    year, full = date_path_parts(date(2026, 1, 5))
    assert year == "2026"
    assert full == "2026-01-05"
