"""EDGAR JSON validators — direct tests."""

from pathlib import Path

import pytest

from timemachine.sources.edgar.config import CAPTURED_FILES, EdgarFile
from timemachine.sources.edgar.validate import (
    validate_company_tickers,
    validate_company_tickers_exchange,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _spec_for(name: str) -> EdgarFile:
    return next(s for s in CAPTURED_FILES if s.name == name)


# --- low-min-bytes specs so the small fixtures pass the size floor ----------


def _tiny_company_tickers_spec() -> EdgarFile:
    return EdgarFile(
        name="company_tickers.json",
        min_bytes=10,
        min_records=1,
        validator=validate_company_tickers,
    )


def _tiny_exchange_spec() -> EdgarFile:
    return EdgarFile(
        name="company_tickers_exchange.json",
        min_bytes=10,
        min_records=1,
        validator=validate_company_tickers_exchange,
    )


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- company_tickers.json --------------------------------------------------


def test_company_tickers_valid_passes():
    result = validate_company_tickers(_read("company_tickers_valid.json"), _tiny_company_tickers_spec())
    assert result.status == "ok"
    assert result.row_count == 5


def test_company_tickers_html_error_is_invalid():
    result = validate_company_tickers(_read("company_tickers_html_error.html"), _tiny_company_tickers_spec())
    assert result.status == "invalid"
    assert result.reason == "html_response"


def test_company_tickers_truncated_is_invalid():
    result = validate_company_tickers(_read("company_tickers_truncated.json"), _tiny_company_tickers_spec())
    assert result.status == "invalid"
    assert result.reason is not None
    assert "json_decode_failed" in result.reason


def test_company_tickers_missing_required_field_is_invalid():
    result = validate_company_tickers(_read("company_tickers_missing_field.json"), _tiny_company_tickers_spec())
    assert result.status == "invalid"
    assert result.reason is not None
    assert "missing_required_fields" in result.reason
    assert "title" in result.reason


def test_company_tickers_extra_field_is_schema_drift_not_rejection():
    result = validate_company_tickers(_read("company_tickers_schema_drift.json"), _tiny_company_tickers_spec())
    assert result.status == "schema_drift"
    assert result.reason is not None
    assert "exchange" in result.reason
    assert result.row_count == 5


def test_company_tickers_below_min_records_is_invalid():
    spec = EdgarFile(
        name="company_tickers.json",
        min_bytes=10,
        min_records=999,  # higher than fixture's 5 records
        validator=validate_company_tickers,
    )
    result = validate_company_tickers(_read("company_tickers_valid.json"), spec)
    assert result.status == "invalid"
    assert result.reason is not None
    assert "below_min_records" in result.reason


def test_company_tickers_below_min_bytes_is_invalid():
    spec = EdgarFile(
        name="company_tickers.json",
        min_bytes=999_999,  # huge floor
        min_records=1,
        validator=validate_company_tickers,
    )
    result = validate_company_tickers(_read("company_tickers_valid.json"), spec)
    assert result.status == "invalid"
    assert result.reason is not None
    assert "below_min_size" in result.reason


# --- company_tickers_exchange.json -----------------------------------------


def test_company_tickers_exchange_valid_passes():
    result = validate_company_tickers_exchange(
        _read("company_tickers_exchange_valid.json"), _tiny_exchange_spec()
    )
    assert result.status == "ok"
    assert result.row_count == 5


def test_company_tickers_exchange_row_width_mismatch_is_invalid():
    result = validate_company_tickers_exchange(
        _read("company_tickers_exchange_row_mismatch.json"), _tiny_exchange_spec()
    )
    assert result.status == "invalid"
    assert result.reason is not None
    assert "row_width_mismatch" in result.reason


@pytest.mark.parametrize("payload", [b"not json at all", b"[]", b"{}"])
def test_company_tickers_garbage_input_is_invalid(payload):
    result = validate_company_tickers(payload, _tiny_company_tickers_spec())
    assert result.status == "invalid"
