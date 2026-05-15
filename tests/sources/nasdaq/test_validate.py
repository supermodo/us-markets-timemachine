import re
from pathlib import Path

import pytest

from timemachine.sources.nasdaq.config import CapturedFile
from timemachine.sources.nasdaq.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"

NASDAQTRADED_HEADER = (
    "Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|"
    "Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares"
)


def _spec(
    *,
    min_bytes: int = 100,
    min_rows: int = 1,
    delimiter: str = "|",
    expected_header: str = NASDAQTRADED_HEADER,
    trailer_pattern: re.Pattern[str] | None = re.compile(r"^File Creation Time:"),
) -> CapturedFile:
    return CapturedFile(
        name="nasdaqtraded.txt",
        delimiter=delimiter,
        expected_header=expected_header,
        min_bytes=min_bytes,
        min_rows=min_rows,
        trailer_pattern=trailer_pattern,
    )


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_valid_file_passes():
    result = validate(_read("nasdaqtraded_valid.txt"), _spec())
    assert result.status == "ok"
    assert result.reason is None
    assert result.row_count == 3
    assert result.file_creation_time is not None
    assert result.file_creation_time.startswith("File Creation Time:")


def test_html_error_page_is_invalid():
    result = validate(_read("nasdaqtraded_html_error.html"), _spec())
    assert result.status == "invalid"
    assert result.reason == "html_response"


def test_below_min_size_is_invalid():
    result = validate(b"tiny", _spec(min_bytes=100))
    assert result.status == "invalid"
    assert result.reason is not None
    assert result.reason.startswith("below_min_size")


def test_truncated_file_is_invalid_below_min_size():
    # Header-only fixture is small; raise min_bytes to force rejection.
    result = validate(_read("nasdaqtraded_truncated.txt"), _spec(min_bytes=10_000))
    assert result.status == "invalid"
    assert result.reason is not None
    assert result.reason.startswith("below_min_size")


def test_wrong_header_is_invalid():
    result = validate(_read("nasdaqtraded_wrong_header.txt"), _spec())
    assert result.status == "invalid"
    assert result.reason == "header_mismatch"


def test_schema_drift_new_trailing_column_is_flagged_not_rejected():
    result = validate(_read("nasdaqtraded_schema_drift.txt"), _spec())
    assert result.status == "schema_drift"
    assert result.reason is not None
    assert "NewExperimentalColumn" in result.reason
    assert result.row_count == 3  # data rows survive the drift


def test_missing_trailer_is_invalid_when_trailer_required():
    result = validate(_read("nasdaqtraded_missing_trailer.txt"), _spec())
    assert result.status == "invalid"
    assert result.reason == "trailer_missing"


def test_no_trailer_required_passes_without_trailer():
    # Models NasdaqWhenIssueWhenDistributed.txt — no "File Creation Time:" trailer.
    result = validate(
        _read("nasdaqtraded_missing_trailer.txt"),
        _spec(trailer_pattern=None),
    )
    assert result.status == "ok"
    # No trailer => row_count includes all lines after header.
    assert result.row_count == 3


def test_csv_trailer_pattern_matches():
    csv_payload = (
        b"evaluation_period,ticker,average_closing_price,round_lot\n"
        b"202603,AAPL,150.25,100\n"
        b"202603,GOOG,2800.00,100\n"
        b"2026-04-01 04:14:17,,,\n"
    )
    spec = _spec(
        delimiter=",",
        expected_header="evaluation_period,ticker,average_closing_price,round_lot",
        trailer_pattern=re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},,,$"),
    )
    result = validate(csv_payload, spec)
    assert result.status == "ok"
    assert result.row_count == 2
    assert result.file_creation_time == "2026-04-01 04:14:17,,,"


def test_below_min_rows_is_invalid():
    result = validate(_read("nasdaqtraded_valid.txt"), _spec(min_rows=100))
    assert result.status == "invalid"
    assert result.reason is not None
    assert result.reason.startswith("below_min_rows")


def test_delimiter_missing_in_data_rows_is_invalid():
    payload = (
        f"{NASDAQTRADED_HEADER}\n"
        "no_delimiter_here\n"
        "File Creation Time: 0101200000:00|||||\n"
    ).encode()
    result = validate(payload, _spec())
    assert result.status == "invalid"
    assert result.reason is not None
    assert result.reason.startswith("delimiter_missing")


@pytest.mark.parametrize(
    "head_bytes",
    [
        b"<!DOCTYPE html><html><body>error</body></html>",
        b"<html><head></head><body>404</body></html>",
        b"   <!doctype HTML PUBLIC ...>\n<html>",  # leading whitespace
    ],
)
def test_html_detection_handles_variants(head_bytes):
    result = validate(head_bytes, _spec(min_bytes=10))
    assert result.status == "invalid"
    assert result.reason == "html_response"
