"""NASDAQ Trader symbol-directory + regulatory archives source.

Captured (overwritten daily by NASDAQ — we snapshot):
    nasdaqtraded.txt, nasdaqlisted.txt, otherlisted.txt,
    TradingSystemAddsDeletes.txt, NasdaqWhenIssueWhenDistributed.txt,
    NasdaqListedRoundLotUpdates.txt

Mirrored (already dated by NASDAQ — we delta-sync):
    regsho/, shorthalts/, regnms/

Discovered (auto-staged for human curation per spec §4.4):
    anything in SymDir/ that is neither captured nor explicitly ignored.
"""

from timemachine.sources.nasdaq.source import NasdaqSource

__all__ = ["NasdaqSource"]
