"""Tests for the mirror-delta job.

Network is mocked via injected lister + fetcher. The integration test in
`test_capture.py` already covers shared plumbing (gzip writes, path layout,
manifest shape); here we focus on the mirror-specific semantics:
  - Filenames that don't match the per-archive pattern are silently skipped.
  - A file already held locally is skipped (idempotency).
  - Fetch failures land as `missing`, not `invalid`.
  - HTML responses land as `invalid` (no on-disk artifact).
  - Listing failure for one archive doesn't affect the others.
"""

import gzip
from pathlib import Path

from timemachine.http import FetchError
from timemachine.sources.nasdaq.mirror import run_mirror


def _make_lister(by_archive: dict[str, list[str]]):
    def list_fn(archive_name: str) -> list[str]:
        if archive_name not in by_archive:
            raise FileNotFoundError(f"no fixture for archive {archive_name}")
        return by_archive[archive_name]

    return list_fn


def _make_fetcher(by_url: dict[str, bytes | Exception]):
    def fetch(url: str) -> bytes:
        result = by_url.get(url)
        if result is None:
            raise FetchError(f"no fixture for {url}")
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


VALID_REGSHO = (
    b"Date|Symbol|Exchange|Status\n"
    b"20240514|AAPL|N|Threshold\n"
    b"20240514|GOOG|Q|Threshold\n"
)
VALID_SHORTHALTS = b"halt_date|halt_time|symbol|trigger\n20240514|10:00:00|AAPL|circuit\n"
VALID_REGNMS = b"date|venue|pilot_group\n20240514|N|A\n"


def test_listing_failure_for_one_archive_records_a_missing_entry_and_continues(tmp_path: Path):
    data_root = tmp_path / "data"
    # regsho fails listing; the other two return empty lists.
    def lister(archive_name: str) -> list[str]:
        if archive_name == "regsho":
            raise ConnectionError("simulated FTP connection refused")
        return []

    entries = run_mirror(
        data_root=data_root,
        lister=lister,
        fetcher=_make_fetcher({}),
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    assert entries[0].status == "missing"
    assert entries[0].name == "regsho/<listing>"
    assert "simulated FTP" in (entries[0].reason or "")


def test_happy_path_stores_files_at_dated_archive_paths(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {
        "regsho": ["nasdaqth20240514.txt"],
        "shorthalts": ["shorthalts20240514.txt"],
        "regnms": ["regnmspilot20240514.txt"],
    }
    fetcher = _make_fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/regsho/nasdaqth20240514.txt": VALID_REGSHO,
            "https://www.nasdaqtrader.com/dynamic/SymDir/shorthalts/shorthalts20240514.txt": VALID_SHORTHALTS,
            "https://www.nasdaqtrader.com/dynamic/SymDir/regnms/regnmspilot20240514.txt": VALID_REGNMS,
        }
    )

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 3
    assert all(e.status == "ok" for e in entries)
    assert all(e.source == "nasdaq" for e in entries)

    # Check paths and content.
    regsho_path = data_root / "nasdaq" / "regsho" / "2024" / "nasdaqth20240514.txt.gz"
    assert regsho_path.exists()
    assert gzip.decompress(regsho_path.read_bytes()) == VALID_REGSHO

    sh_path = data_root / "nasdaq" / "shorthalts" / "2024" / "shorthalts20240514.txt.gz"
    assert sh_path.exists()

    nms_path = data_root / "nasdaq" / "regnms" / "2024" / "regnmspilot20240514.txt.gz"
    assert nms_path.exists()


def test_filenames_not_matching_pattern_are_silently_skipped(tmp_path: Path):
    data_root = tmp_path / "data"
    # One garbage filename + one good filename in the same listing.
    listings = {
        "regsho": [
            "Reg SHO Security Summary Jan 2 2007.txt",  # doesn't match pattern
            "nasdaqth20240514.txt",  # matches
        ],
        "shorthalts": [],
        "regnms": [],
    }
    fetcher = _make_fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/regsho/nasdaqth20240514.txt": VALID_REGSHO,
        }
    )

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    # Only the matching file generates an entry; the garbage filename produces nothing.
    assert len(entries) == 1
    assert entries[0].name == "regsho/nasdaqth20240514.txt"
    assert entries[0].status == "ok"


def test_idempotency_existing_file_is_skipped(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {"regsho": ["nasdaqth20240514.txt"], "shorthalts": [], "regnms": []}
    fetcher_calls: list[str] = []

    def counting_fetcher(url: str) -> bytes:
        fetcher_calls.append(url)
        return VALID_REGSHO

    # First run — fetches once.
    run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=counting_fetcher,
        sleep=lambda _s: None,
    )
    assert len(fetcher_calls) == 1

    # Second run — file is already on disk; fetcher must NOT be called.
    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=counting_fetcher,
        sleep=lambda _s: None,
    )
    assert len(fetcher_calls) == 1  # unchanged
    assert entries == []  # no work to report


def test_fetch_error_records_missing_status_with_no_disk_artifact(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {"regsho": ["nasdaqth20240514.txt"], "shorthalts": [], "regnms": []}
    fetcher = _make_fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/regsho/nasdaqth20240514.txt": FetchError(
                "simulated 500"
            ),
        }
    )

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    assert entries[0].status == "missing"
    assert "simulated 500" in (entries[0].reason or "")
    assert not (data_root / "nasdaq" / "regsho").exists()


def test_html_response_records_invalid_no_disk_artifact(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {"regsho": ["nasdaqth20240514.txt"], "shorthalts": [], "regnms": []}
    fetcher = _make_fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/regsho/nasdaqth20240514.txt": (
                b"<!DOCTYPE html><html><body>404</body></html>"
            ),
        }
    )

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    assert entries[0].status == "invalid"
    assert entries[0].reason == "html_response"
    assert entries[0].stored_path is None
    assert not (data_root / "nasdaq" / "regsho").exists()


def test_max_per_archive_limits_fetches(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {
        "regsho": [
            "nasdaqth20240501.txt",
            "nasdaqth20240502.txt",
            "nasdaqth20240503.txt",
            "nasdaqth20240506.txt",
            "nasdaqth20240507.txt",
        ],
        "shorthalts": [],
        "regnms": [],
    }

    def fetcher(_url: str) -> bytes:
        return VALID_REGSHO

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        max_per_archive=2,
        sleep=lambda _s: None,
    )

    assert len(entries) == 2
    assert all(e.status == "ok" for e in entries)


def test_invalid_date_in_filename_is_silently_skipped(tmp_path: Path):
    data_root = tmp_path / "data"
    listings = {
        "regsho": ["nasdaqth20241332.txt"],  # 13th month, invalid date
        "shorthalts": [],
        "regnms": [],
    }
    fetcher = _make_fetcher({})

    entries = run_mirror(
        data_root=data_root,
        lister=_make_lister(listings),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert entries == []
