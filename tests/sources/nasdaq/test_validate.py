import re
from pathlib import Path

import pytest

from timemachine.sources.nasdaq.config import CapturedFile, captured_by_name
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


def _round_lot_payload(header: str, rows: list[str], trailer: str) -> bytes:
    return ("\n".join([header, *rows, trailer]) + "\n").encode()


ROUND_LOT_SPEC = captured_by_name("NasdaqListedRoundLotUpdates.txt")


def test_round_lot_updates_current_format_is_ok():
    # Format NASDAQ publishes since 2026-10-01: `issue_id` inserted as column 2,
    # trailer padded to five fields.
    rows = [f"202609,{20000 + i},T{i:05d},236.25285714,100" for i in range(1_200)]
    payload = _round_lot_payload(
        "evaluation_period,issue_id,ticker,average_closing_price,round_lot",
        rows,
        "2026-10-01 02:35:26,,,,",
    )
    assert ROUND_LOT_SPEC is not None
    result = validate(payload, ROUND_LOT_SPEC)
    assert result.status == "ok"
    assert result.row_count == 1_200
    assert result.file_creation_time == "2026-10-01 02:35:26,,,,"


def test_round_lot_updates_pre_october_2026_format_is_header_mismatch():
    rows = [f"202608,T{i:05d},236.25285714,100" for i in range(1_200)]
    payload = _round_lot_payload(
        "evaluation_period,ticker,average_closing_price,round_lot",
        rows,
        "2026-09-01 02:35:26,,,",
    )
    assert ROUND_LOT_SPEC is not None
    result = validate(payload, ROUND_LOT_SPEC)
    assert result.status == "invalid"
    assert result.reason == "header_mismatch"


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
