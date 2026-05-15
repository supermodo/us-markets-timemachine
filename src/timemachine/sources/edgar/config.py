"""Declared file list and validation specs for EDGAR ticker-mapping capture.

Both files live at `https://www.sec.gov/files/`. They are overwritten in place
daily and the SEC keeps no public history of prior versions.

Sizes are sanity floors (current values are ~150 KB and ~250 KB respectively).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from timemachine.sources.edgar.validate import (
    ValidationResult,
    validate_company_tickers,
    validate_company_tickers_exchange,
)

EDGAR_FILES_BASE = "https://www.sec.gov/files/"


@dataclass(frozen=True)
class EdgarFile:
    name: str
    min_bytes: int
    min_records: int
    validator: Callable[[bytes, "EdgarFile"], ValidationResult]

    @property
    def url(self) -> str:
        return f"{EDGAR_FILES_BASE}{self.name}"

    @property
    def dir_name(self) -> str:
        return Path(self.name).stem


CAPTURED_FILES: tuple[EdgarFile, ...] = (
    EdgarFile(
        name="company_tickers.json",
        min_bytes=100_000,   # current ~150 KB
        min_records=5_000,   # current ~10k records
        validator=validate_company_tickers,
    ),
    EdgarFile(
        name="company_tickers_exchange.json",
        min_bytes=100_000,   # current ~250 KB
        min_records=5_000,   # current ~10k records
        validator=validate_company_tickers_exchange,
    ),
)
