"""The Source protocol every data source must implement.

A `Source` is a self-contained unit that knows how to snapshot one upstream
publisher's "vanishing" files for a given date. The framework gives it a
`data_root` and a `today`; it returns a list of `FileEntry` recording what was
captured, validated, rejected, or missing — and writes any successful payload
under `data/<source.name>/...` (using the helpers in `timemachine.paths`).

The contract is intentionally minimal:

    * `name`         — short directory-safe identifier (e.g. "nasdaq", "edgar").
                        Used for `data/<name>/...`, `manifest-<name>-*.json`,
                        and the `--only <name>` / `--exclude <name>` CLI flags.

    * `display_name` — human-readable label for logs and notifications.

    * `should_run(today)` — cheap calendar gate. Returns False on days the
                            upstream publisher does not produce data (weekends,
                            US market holidays, off-cadence days). The framework
                            calls this before `snapshot()` and records a
                            `skipped` entry in the manifest when False.

    * `snapshot(...)` — the actual work. Fetch upstream files, validate, write
                        gzipped copies, return one FileEntry per file. The
                        source decides internally whether it does capture,
                        mirror, discovery, or any combination. Failures must
                        be returned as `missing`/`invalid` entries rather than
                        raised — one source failing must not crash the run.

This minimalism is deliberate. A larger contract (e.g. forcing every source
into a 3-phase capture+mirror+discover shape) would push NASDAQ's quirks onto
sources that don't share them — EDGAR's `company_tickers.json` is a single
fetch, not a discovery problem. Sources that DO need multiple phases
(NASDAQ) compose them privately inside their own `snapshot()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from timemachine.manifest import FileEntry


@runtime_checkable
class Source(Protocol):
    name: str
    display_name: str

    def should_run(self, today: date) -> bool: ...

    def snapshot(
        self,
        *,
        data_root: Path,
        today: date,
        dry_run: bool = False,
    ) -> Iterable[FileEntry]: ...
