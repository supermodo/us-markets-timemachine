"""Tests for the discovery + staging-area job.

Discovery rules under test:
  - Captured files in the listing → silently ignored.
  - IGNORED_FILES files in the listing → silently ignored.
  - Known directories (MIRRORED_ARCHIVES + IGNORED_ARCHIVES) → silently ignored.
  - Unknown file → auto-fetched, validated, staged in `data/_discovered/...`,
    status="discovered". NEVER stored at the canonical path.
  - Unknown directory → flagged (status="discovered") but NOT traversed.
  - Fetch failure for an unknown file → status="missing" with reason.
  - HTML for an unknown file → status="invalid", no on-disk artifact.
  - Re-running on the same day where the unknown is already staged →
    status="discovered" with "already staged for today" note (idempotent).
  - Listing failure → single "discovery:<listing>" entry, status="missing".
"""

import gzip
from datetime import date
from pathlib import Path

from timemachine.http import FetchError
from timemachine.sources.nasdaq.discovery import SymDirEntry, run_discovery

TODAY = date(2026, 5, 14)


def _lister(items: list[SymDirEntry]):
    def fn() -> list[SymDirEntry]:
        return items

    return fn


def _fetcher(by_url: dict[str, bytes | Exception]):
    def fn(url: str) -> bytes:
        result = by_url.get(url)
        if result is None:
            raise FetchError(f"no fixture for {url}")
        if isinstance(result, Exception):
            raise result
        return result

    return fn


def test_known_captured_and_ignored_files_produce_no_entries(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [
        SymDirEntry("nasdaqtraded.txt", False),  # captured
        SymDirEntry("nasdaqlisted.txt", False),  # captured
        SymDirEntry("options.txt", False),  # ignored
        SymDirEntry("regsho", True),  # known mirrored archive
        SymDirEntry("regshopilot", True),  # ignored archive
    ]
    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=_fetcher({}),
        sleep=lambda _s: None,
    )
    assert entries == []


def test_unknown_file_is_auto_staged_in_discovered_folder(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("brandnewfile.txt", False)]
    payload = b"some\tcontent\tfor\tnewfile\n"
    fetcher = _fetcher(
        {"https://www.nasdaqtrader.com/dynamic/SymDir/brandnewfile.txt": payload}
    )

    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    e = entries[0]
    assert e.name == "discovery:brandnewfile.txt"
    assert e.status == "discovered"
    assert e.source == "nasdaq"
    assert e.stored_path == "data/nasdaq/_discovered/brandnewfile.txt/2026/2026-05-14.gz"
    assert e.reason == "unknown file auto-staged; human curation required"

    staged = data_root / "nasdaq" / "_discovered" / "brandnewfile.txt" / "2026" / "2026-05-14.gz"
    assert staged.exists()
    assert gzip.decompress(staged.read_bytes()) == payload


def test_unknown_file_NEVER_lands_at_canonical_path(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("brandnewfile.txt", False)]
    fetcher = _fetcher(
        {"https://www.nasdaqtrader.com/dynamic/SymDir/brandnewfile.txt": b"hello\n"}
    )

    run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    # Canonical-path-style: `data/nasdaq/brandnewfile/2026/2026-05-14.txt.gz` — must NOT exist.
    assert not (data_root / "nasdaq" / "brandnewfile").exists()


def test_unknown_directory_is_flagged_but_not_traversed(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("brandnewdir", True)]
    # No fetcher entries — confirms no fetch is attempted.
    fetcher = _fetcher({})

    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    e = entries[0]
    assert e.name == "discovery:brandnewdir/"
    assert e.status == "discovered"
    assert "not auto-traversed" in (e.reason or "")
    assert e.stored_path is None


def test_unknown_file_fetch_failure_records_missing(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("mystery.txt", False)]
    fetcher = _fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/mystery.txt": FetchError(
                "simulated network blip"
            )
        }
    )

    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    e = entries[0]
    assert e.status == "missing"
    assert "simulated network blip" in (e.reason or "")
    assert e.stored_path is None


def test_unknown_file_returning_html_records_invalid_no_disk_artifact(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("mystery.txt", False)]
    fetcher = _fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/mystery.txt": (
                b"<!doctype html><html><body>nope</body></html>"
            )
        }
    )

    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    e = entries[0]
    assert e.status == "invalid"
    assert "html_response" in (e.reason or "")
    assert e.stored_path is None
    assert not (data_root / "nasdaq" / "_discovered").exists()


def test_listing_failure_returns_single_listing_entry(tmp_path: Path):
    data_root = tmp_path / "data"

    def broken() -> list[SymDirEntry]:
        raise ConnectionError("simulated FTP refused")

    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=broken,
        fetcher=_fetcher({}),
        sleep=lambda _s: None,
    )

    assert len(entries) == 1
    e = entries[0]
    assert e.name == "discovery:<listing>"
    assert e.status == "missing"
    assert "simulated FTP" in (e.reason or "")


def test_same_day_rerun_is_idempotent_on_already_staged_file(tmp_path: Path):
    data_root = tmp_path / "data"
    items = [SymDirEntry("brandnewfile.txt", False)]
    payload = b"row1\nrow2\nrow3\n"
    fetcher = _fetcher(
        {"https://www.nasdaqtrader.com/dynamic/SymDir/brandnewfile.txt": payload}
    )

    # First run: stages the file.
    run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher,
        sleep=lambda _s: None,
    )

    staged = data_root / "nasdaq" / "_discovered" / "brandnewfile.txt" / "2026" / "2026-05-14.gz"
    original_bytes = staged.read_bytes()

    # Second run with different payload: the staged file is NOT overwritten.
    fetcher2 = _fetcher(
        {
            "https://www.nasdaqtrader.com/dynamic/SymDir/brandnewfile.txt": b"DIFFERENT_PAYLOAD\n"
        }
    )
    entries = run_discovery(
        data_root=data_root,
        today=TODAY,
        lister=_lister(items),
        fetcher=fetcher2,
        sleep=lambda _s: None,
    )

    assert entries[0].reason == "already staged for today"
    assert staged.read_bytes() == original_bytes
