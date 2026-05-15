"""Source registry — one explicit import per source.

Adding a new source is an explicit, greppable, reviewable act:

    1. Implement the source under `src/timemachine/sources/<name>/`,
       satisfying the `Source` protocol from `sources/base.py`.
    2. Add an import below.
    3. Add a `REGISTRY[<name>] = <Cls>()` line.
    4. Add tests under `tests/sources/<name>/`.
    5. Add a notice file at `data/<name>/NOTICE.md`.
    6. Update `docs/POTENTIAL-SOURCES.md` to mark integrated.

No filesystem auto-discovery, no entry-point magic — what's shipped is what's
imported here. This keeps the bar for accepting a new source visible at one
file: this one.
"""

from timemachine.sources.base import Source
from timemachine.sources.edgar import EdgarSource
from timemachine.sources.nasdaq import NasdaqSource

REGISTRY: dict[str, Source] = {
    NasdaqSource.name: NasdaqSource(),
    EdgarSource.name: EdgarSource(),
}

__all__ = ["REGISTRY", "Source"]
