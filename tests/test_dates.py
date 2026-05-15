from datetime import date

from timemachine.dates import date_path_parts, et_today, now_utc_iso


def test_et_today_returns_a_date():
    d = et_today()
    assert isinstance(d, date)
    # Sanity bracket: not before this project's launch year, not absurdly future.
    assert 2025 <= d.year <= 2100


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
