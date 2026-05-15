"""Declared file list and validation specs for the daily capture job.

A file is captured if and only if it appears in CAPTURED_FILES. Files seen in
NASDAQ's SymDir/ index that are neither captured nor in IGNORED_FILES become
discovery findings (spec section 4.4).
"""

import re
from dataclasses import dataclass

SYMDIR_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir/"


@dataclass(frozen=True)
class CapturedFile:
    name: str
    delimiter: str
    expected_header: str
    min_bytes: int
    min_rows: int
    trailer_pattern: re.Pattern[str] | None

    @property
    def url(self) -> str:
        return f"{SYMDIR_BASE}{self.name}"

    @property
    def dir_name(self) -> str:
        return self.name.removesuffix(".txt").removesuffix(".csv")


_FCT = re.compile(r"^File Creation Time:")
_RLU_TRAILER = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},,,$")


CAPTURED_FILES: tuple[CapturedFile, ...] = (
    CapturedFile(
        name="nasdaqtraded.txt",
        delimiter="|",
        expected_header=(
            "Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|"
            "Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares"
        ),
        min_bytes=200_000,
        min_rows=5_000,
        trailer_pattern=_FCT,
    ),
    CapturedFile(
        name="nasdaqlisted.txt",
        delimiter="|",
        expected_header=(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares"
        ),
        min_bytes=80_000,
        min_rows=2_000,
        trailer_pattern=_FCT,
    ),
    CapturedFile(
        name="otherlisted.txt",
        delimiter="|",
        expected_header=(
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
            "Test Issue|NASDAQ Symbol"
        ),
        min_bytes=100_000,
        min_rows=3_000,
        trailer_pattern=_FCT,
    ),
    CapturedFile(
        name="TradingSystemAddsDeletes.txt",
        delimiter="|",
        expected_header=(
            "Symbol|Company Name|NASDAQ Action|BX Action|PSX Action|Effective Date|"
            "Primary Listing Market"
        ),
        # Variable in size: event-driven; some days only one or two actions.
        min_bytes=100,
        min_rows=1,
        trailer_pattern=_FCT,
    ),
    CapturedFile(
        name="NasdaqWhenIssueWhenDistributed.txt",
        delimiter="|",
        expected_header="Effective Date|Issue Name|Symbol|When Issued Flag|When Distributed Flag",
        min_bytes=10_000,
        min_rows=100,
        # No "File Creation Time:" trailer; each data row carries its own timestamp.
        trailer_pattern=None,
    ),
    CapturedFile(
        name="NasdaqListedRoundLotUpdates.txt",
        delimiter=",",
        expected_header="evaluation_period,ticker,average_closing_price,round_lot",
        min_bytes=30_000,
        min_rows=1_000,
        # CSV trailer: "YYYY-MM-DD HH:MM:SS,,," — empty-field timestamp line.
        trailer_pattern=_RLU_TRAILER,
    ),
)


# Files seen in SymDir/ that we deliberately do NOT capture or surface as discoveries.
# Spec section 3.3 + interview answers.
IGNORED_FILES: frozenset[str] = frozenset(
    {
        # Options pricing / position files (spec section 3.3)
        "options.txt",
        "bxoptions.txt",
        "phlxoptions.csv",
        # Options strike-ID ZIPs — all venues (spec section 3.3, the "*ListedStrikesWithOptionIds set")
        "nasdaqListedStrikesWithOptionIds.zip",
        "phlxListedStrikesWithOptionIds.zip",
        "bxListedStrikesWithOptionIds.zip",
        "gmniListedStrikesWithOptionIds.zip",
        "iseListedStrikesWithOptionIds.zip",
        "mcryListedStrikesWithOptionIds.zip",
        "mcryListedStrikesWithOptionIds_old.zip",
        "phlxStrikesOld.zip",
        # Stale / dead
        "bondslist.txt",
        "otclist.txt",
        "pbot.csv",
        "bxo_lmm.csv",
        # Marginal — deferred until concrete need
        "bxtraded.txt",
        "psxtraded.txt",
        "mpidlist.txt",
    }
)


MIRRORED_ARCHIVES: tuple[str, ...] = ("regsho", "shorthalts", "regnms")

# Archive directories deliberately out of scope.
# Reg SHO Pilot Program (regshopilot, regshopilotlist) ended in 2007 — historical
# only, not vanishing. NASDAQ exposes the directory via FTP but blocks HTTPS browsing.
IGNORED_ARCHIVES: frozenset[str] = frozenset({"regshopilot", "regshopilotlist"})


def captured_by_name(name: str) -> CapturedFile | None:
    for f in CAPTURED_FILES:
        if f.name == name:
            return f
    return None
