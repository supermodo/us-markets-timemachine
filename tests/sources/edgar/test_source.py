"""EdgarSource integration tests.

The fetcher is injected so no network is touched. We verify:
  - happy path stores both files at namespaced canonical paths
  - HTML response is parked under data/edgar/_rejected/
  - fetch error → status="missing", nothing on disk
  - schema drift is stored at canonical path with status "schema_drift"
  - User-Agent passed to fetcher includes the contact email
  - missing TIMEMACHINE_CONTACT_EMAIL falls back to the project default
  - malformed contact email raises EdgarConfigError
  - should_run() returns False on weekends
"""

from __future__ import annotations

import gzip
from datetime import date
from pathlib import Path

import pytest

from timemachine.http import FetchError
from timemachine.sources.edgar.config import EdgarFile
from timemachine.sources.edgar.source import (
    CONTACT_ENV_VAR,
    DEFAULT_CONTACT_EMAIL,
    EdgarConfigError,
    EdgarSource,
    _build_user_agent,
    _resolve_contact_email,
)
from timemachine.sources.edgar.validate import (
    validate_company_tickers,
    validate_company_tickers_exchange,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Tiny specs so small fixtures pass the size/record floors.
TINY_SPECS = (
    EdgarFile(
        name="company_tickers.json",
        min_bytes=10,
        min_records=1,
        validator=validate_company_tickers,
    ),
    EdgarFile(
        name="company_tickers_exchange.json",
        min_bytes=10,
        min_records=1,
        validator=validate_company_tickers_exchange,
    ),
)
WEEKDAY = date(2026, 5, 14)  # Thursday


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fetcher_returning(by_url: dict[str, bytes | Exception]):
    captured: list[dict] = []

    def fetch(url: str, **kwargs):
        captured.append({"url": url, **kwargs})
        result = by_url.get(url)
        if result is None:
            raise FetchError(f"no fixture for {url}")
        if isinstance(result, Exception):
            raise result
        return result

    fetch.calls = captured  # type: ignore[attr-defined]
    return fetch


def test_should_run_skips_weekends():
    src = EdgarSource()
    assert src.should_run(date(2026, 5, 14)) is True   # Thursday
    assert src.should_run(date(2026, 5, 16)) is False  # Saturday
    assert src.should_run(date(2026, 5, 17)) is False  # Sunday


def test_happy_path_stores_both_files_under_data_edgar(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "tester@example.com")
    data_root = tmp_path / "data"
    fetcher = _fetcher_returning(
        {
            "https://www.sec.gov/files/company_tickers.json": _read("company_tickers_valid.json"),
            "https://www.sec.gov/files/company_tickers_exchange.json": _read(
                "company_tickers_exchange_valid.json"
            ),
        }
    )
    src = EdgarSource(specs=TINY_SPECS)

    entries = list(src.snapshot(data_root=data_root, today=WEEKDAY, fetcher=fetcher))

    assert len(entries) == 2
    assert all(e.status == "ok" for e in entries)
    assert all(e.source == "edgar" for e in entries)

    ct = data_root / "edgar" / "company_tickers" / "2026" / "2026-05-14.gz"
    cte = data_root / "edgar" / "company_tickers_exchange" / "2026" / "2026-05-14.gz"
    assert ct.exists()
    assert cte.exists()
    assert b"AAPL" in gzip.decompress(ct.read_bytes())


def test_user_agent_includes_contact_email(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "tester@example.com")
    fetcher = _fetcher_returning(
        {
            "https://www.sec.gov/files/company_tickers.json": _read("company_tickers_valid.json"),
            "https://www.sec.gov/files/company_tickers_exchange.json": _read(
                "company_tickers_exchange_valid.json"
            ),
        }
    )
    EdgarSource(specs=TINY_SPECS).snapshot(
        data_root=tmp_path / "data", today=WEEKDAY, fetcher=fetcher, dry_run=True
    )
    for call in fetcher.calls:
        assert "tester@example.com" in call["user_agent"]


def test_missing_contact_email_env_falls_back_to_project_default(monkeypatch):
    monkeypatch.delenv(CONTACT_ENV_VAR, raising=False)
    assert _resolve_contact_email() == DEFAULT_CONTACT_EMAIL


def test_malformed_contact_email_is_a_loud_startup_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "not an email")
    fetcher = _fetcher_returning({})
    with pytest.raises(EdgarConfigError) as exc:
        list(
            EdgarSource(specs=TINY_SPECS).snapshot(
                data_root=tmp_path / "data", today=WEEKDAY, fetcher=fetcher
            )
        )
    assert "must be a single email address" in str(exc.value)


def test_html_response_parks_in_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "tester@example.com")
    data_root = tmp_path / "data"
    fetcher = _fetcher_returning(
        {
            "https://www.sec.gov/files/company_tickers.json": _read("company_tickers_html_error.html"),
            "https://www.sec.gov/files/company_tickers_exchange.json": _read(
                "company_tickers_exchange_valid.json"
            ),
        }
    )

    entries = list(
        EdgarSource(specs=TINY_SPECS).snapshot(
            data_root=data_root, today=WEEKDAY, fetcher=fetcher
        )
    )

    bad = next(e for e in entries if e.status == "invalid")
    assert bad.reason == "html_response"
    assert bad.stored_path == "data/edgar/_rejected/2026/2026-05-14/company_tickers.json.gz"
    rejected = data_root / "edgar" / "_rejected" / "2026" / "2026-05-14" / "company_tickers.json.gz"
    assert rejected.exists()
    # Canonical path must NOT exist for the bad file.
    assert not (data_root / "edgar" / "company_tickers" / "2026" / "2026-05-14.gz").exists()


def test_fetch_error_records_missing_status(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "tester@example.com")
    fetcher = _fetcher_returning(
        {
            "https://www.sec.gov/files/company_tickers.json": FetchError("simulated 503"),
            "https://www.sec.gov/files/company_tickers_exchange.json": _read(
                "company_tickers_exchange_valid.json"
            ),
        }
    )
    entries = list(
        EdgarSource(specs=TINY_SPECS).snapshot(
            data_root=tmp_path / "data", today=WEEKDAY, fetcher=fetcher
        )
    )
    missing = next(e for e in entries if e.status == "missing")
    assert "simulated 503" in (missing.reason or "")
    assert missing.stored_path is None


def test_schema_drift_is_stored_at_canonical_path_with_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(CONTACT_ENV_VAR, "tester@example.com")
    data_root = tmp_path / "data"
    fetcher = _fetcher_returning(
        {
            "https://www.sec.gov/files/company_tickers.json": _read("company_tickers_schema_drift.json"),
            "https://www.sec.gov/files/company_tickers_exchange.json": _read(
                "company_tickers_exchange_valid.json"
            ),
        }
    )
    entries = list(
        EdgarSource(specs=TINY_SPECS).snapshot(
            data_root=data_root, today=WEEKDAY, fetcher=fetcher
        )
    )
    drift = next(e for e in entries if e.status == "schema_drift")
    assert "exchange" in (drift.reason or "")
    assert (data_root / "edgar" / "company_tickers" / "2026" / "2026-05-14.gz").exists()


def test_real_registry_includes_edgar():
    from timemachine.sources import REGISTRY

    assert "edgar" in REGISTRY
    assert REGISTRY["edgar"].display_name.startswith("SEC EDGAR")


def test_build_user_agent_format():
    ua = _build_user_agent("ops@example.com")
    assert ua.startswith("us-markets-timemachine/")
    assert "ops@example.com" in ua
