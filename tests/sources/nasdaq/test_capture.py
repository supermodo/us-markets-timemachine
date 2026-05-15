"""Integration test for the capture job — exercises the full pipeline
(fetch via injected fetcher → validate → write or reject → return FileEntry)
without touching the network.
"""

import gzip
import re
from datetime import date
from pathlib import Path

import pytest

from timemachine.http import FetchError
from timemachine.sources.nasdaq.capture import run_capture
from timemachine.sources.nasdaq.config import CapturedFile

FIXTURES = Path(__file__).parent / "fixtures"

# A test spec calibrated so the small fixture files (3 data rows) pass.
SPEC = CapturedFile(
    name="nasdaqtraded.txt",
    delimiter="|",
    expected_header=(
        "Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|"
        "Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares"
    ),
    min_bytes=100,
    min_rows=1,
    trailer_pattern=re.compile(r"^File Creation Time:"),
)
SPECS = (SPEC,)

TODAY = date(2026, 5, 14)


def _fetcher_returning(content: bytes):
    def fetch(url: str) -> bytes:
        return content

    return fetch


def _fetcher_raising(exc: Exception):
    def fetch(url: str) -> bytes:
        raise exc

    return fetch


def test_happy_path_stores_at_dated_canonical_path(tmp_path: Path):
    data_root = tmp_path / "data"
    payload = (FIXTURES / "nasdaqtraded_valid.txt").read_bytes()

    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(payload),
        today=TODAY,
        specs=SPECS,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.status == "ok"
    assert entry.row_count == 3
    assert entry.reason is None
    assert entry.source == "nasdaq"
    assert entry.stored_path == "data/nasdaq/nasdaqtraded/2026/2026-05-14.txt.gz"

    stored = data_root / "nasdaq" / "nasdaqtraded" / "2026" / "2026-05-14.txt.gz"
    assert stored.exists()
    assert gzip.decompress(stored.read_bytes()) == payload


def test_html_response_parks_under_rejected(tmp_path: Path):
    data_root = tmp_path / "data"
    html = (FIXTURES / "nasdaqtraded_html_error.html").read_bytes()

    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(html),
        today=TODAY,
        specs=SPECS,
    )

    entry = entries[0]
    assert entry.status == "invalid"
    assert entry.reason == "html_response"
    assert entry.stored_path == "data/nasdaq/_rejected/2026/2026-05-14/nasdaqtraded.txt.gz"

    # Canonical path must NOT exist.
    assert not (data_root / "nasdaq" / "nasdaqtraded" / "2026" / "2026-05-14.txt.gz").exists()
    # Rejected path DOES exist with the original bytes.
    rejected = data_root / "nasdaq" / "_rejected" / "2026" / "2026-05-14" / "nasdaqtraded.txt.gz"
    assert rejected.exists()
    assert gzip.decompress(rejected.read_bytes()) == html


def test_fetch_error_records_missing_status(tmp_path: Path):
    data_root = tmp_path / "data"

    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_raising(FetchError("simulated network blip")),
        today=TODAY,
        specs=SPECS,
    )

    entry = entries[0]
    assert entry.status == "missing"
    assert entry.stored_path is None
    assert entry.sha256 is None
    assert "simulated network blip" in (entry.reason or "")
    # Nothing on disk.
    assert not (data_root / "nasdaq" / "nasdaqtraded").exists()


def test_schema_drift_is_stored_at_canonical_path_with_flag(tmp_path: Path):
    data_root = tmp_path / "data"
    payload = (FIXTURES / "nasdaqtraded_schema_drift.txt").read_bytes()

    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(payload),
        today=TODAY,
        specs=SPECS,
    )

    entry = entries[0]
    assert entry.status == "schema_drift"
    assert entry.reason is not None
    assert "NewExperimentalColumn" in entry.reason
    # File IS stored at the canonical dated path (spec §4.3: lenient — store + flag).
    assert entry.stored_path == "data/nasdaq/nasdaqtraded/2026/2026-05-14.txt.gz"
    assert (data_root / "nasdaq" / "nasdaqtraded" / "2026" / "2026-05-14.txt.gz").exists()


def test_existing_dated_file_is_never_overwritten(tmp_path: Path):
    data_root = tmp_path / "data"
    payload = (FIXTURES / "nasdaqtraded_valid.txt").read_bytes()

    # First run captures.
    run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(payload),
        today=TODAY,
        specs=SPECS,
    )
    stored = data_root / "nasdaq" / "nasdaqtraded" / "2026" / "2026-05-14.txt.gz"
    original_bytes = stored.read_bytes()

    # Second run with DIFFERENT payload — must NOT overwrite.
    different_payload = payload + b"\nY|EXTRA|Sneaky Late Addition||||100|N||EXTRA|EXTRA|N\n"
    entries2 = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(different_payload),
        today=TODAY,
        specs=SPECS,
    )
    assert entries2[0].status == "ok"
    assert entries2[0].reason == "already_existed_not_overwritten"
    assert stored.read_bytes() == original_bytes


def test_dry_run_returns_entries_but_writes_no_files(tmp_path: Path):
    data_root = tmp_path / "data"
    payload = (FIXTURES / "nasdaqtraded_valid.txt").read_bytes()

    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(payload),
        today=TODAY,
        specs=SPECS,
        dry_run=True,
    )

    assert entries[0].status == "ok"
    # Status is reported, but no file written.
    assert not data_root.exists()


@pytest.mark.parametrize(
    "fixture,expected_status,expected_reason_fragment,expected_path_dir",
    [
        ("nasdaqtraded_valid.txt", "ok", None, "nasdaq/nasdaqtraded"),
        ("nasdaqtraded_html_error.html", "invalid", "html_response", "nasdaq/_rejected"),
        ("nasdaqtraded_wrong_header.txt", "invalid", "header_mismatch", "nasdaq/_rejected"),
        ("nasdaqtraded_missing_trailer.txt", "invalid", "trailer_missing", "nasdaq/_rejected"),
        ("nasdaqtraded_schema_drift.txt", "schema_drift", "NewExperimentalColumn", "nasdaq/nasdaqtraded"),
    ],
)
def test_capture_pipeline_matrix(
    tmp_path: Path,
    fixture: str,
    expected_status: str,
    expected_reason_fragment: str | None,
    expected_path_dir: str,
):
    data_root = tmp_path / "data"
    payload = (FIXTURES / fixture).read_bytes()
    entries = run_capture(
        data_root=data_root,
        fetcher=_fetcher_returning(payload),
        today=TODAY,
        specs=SPECS,
    )
    entry = entries[0]
    assert entry.status == expected_status
    assert entry.source == "nasdaq"
    if expected_reason_fragment is not None:
        assert entry.reason is not None
        assert expected_reason_fragment in entry.reason
    assert expected_path_dir in (entry.stored_path or "")
