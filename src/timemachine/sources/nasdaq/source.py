"""NasdaqSource — implements the Source protocol for the NASDAQ Trader feed.

snapshot() runs the three NASDAQ-specific phases in order:
    1. capture    — declared §3.1 files, NASDAQ overwrites daily.
    2. mirror     — §3.2 archived directories (regsho/shorthalts/regnms).
    3. discovery  — §4.4 auto-stage any new files that appeared upstream.

This wrapper keeps `daily.py` (and the future `cli.py`) free of any NASDAQ
constants. Callers see a single `snapshot()` returning a flat list of
FileEntry — exactly the contract `sources/base.py` defines.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from timemachine.manifest import FileEntry
from timemachine.sources.nasdaq.capture import run_capture
from timemachine.sources.nasdaq.discovery import run_discovery
from timemachine.sources.nasdaq.mirror import run_mirror


@dataclass(frozen=True)
class NasdaqSource:
    name: str = "nasdaq"
    display_name: str = "NASDAQ Trader Symbol Directory"

    def should_run(self, today: date) -> bool:
        # NASDAQ refreshes the symbol-directory files every day, including
        # weekends in many cases (the trailer time may not advance on a
        # non-trading day, but the file is still rewritten). Run unconditionally;
        # the existing validators handle "stale but well-formed" gracefully.
        del today
        return True

    def snapshot(
        self,
        *,
        data_root: Path,
        today: date,
        dry_run: bool = False,
    ) -> Iterable[FileEntry]:
        capture_entries = run_capture(data_root=data_root, today=today, dry_run=dry_run)
        mirror_entries = run_mirror(data_root=data_root, dry_run=dry_run)
        discovery_entries = run_discovery(data_root=data_root, today=today, dry_run=dry_run)
        return [*capture_entries, *mirror_entries, *discovery_entries]
