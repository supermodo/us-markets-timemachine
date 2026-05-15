"""us-markets-timemachine — multi-source CLI.

    us-markets-timemachine daily [--output-dir DIR] [--dry-run]
                                 [--only nasdaq[,edgar]] [--exclude edgar]
                                 [--no-notify]
    us-markets-timemachine list-sources

The `daily` subcommand iterates the source REGISTRY, runs `snapshot()` on each
selected source, and writes a per-source append-only manifest at
`data/<source>/manifest-daily.json`. Sources that return any
`invalid` / `missing` entries cause the process to exit 1 (so CI goes red and
notifications fire). `schema_drift` and `discovered` are flags, not failures.

The CLI surface is intentionally uniform — there are no source-specific flags
here. Per-source tuning (e.g. `NasdaqSource.mirror_max_per_archive`) belongs
on the source dataclass itself, where it composes with the `Source` protocol
and stays out of every other source's CLI help text.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from timemachine.dates import et_today, now_utc_iso
from timemachine.manifest import FileEntry, RunEntry, append_run
from timemachine.notify import emit_notifications, needs_notification
from timemachine.paths import manifest_path
from timemachine.sources import REGISTRY, Source

EXIT_OK = 0
EXIT_ANOMALY = 1
EXIT_BAD_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.subcommand == "list-sources":
        return _list_sources(today=et_today())
    if args.subcommand == "daily":
        return _run_daily(args)
    raise AssertionError(f"unhandled subcommand: {args.subcommand!r}")  # argparse should prevent


# ---------------------------------------------------------------------------
# `daily` subcommand
# ---------------------------------------------------------------------------


def _run_daily(args: argparse.Namespace) -> int:
    today = et_today()
    try:
        selected = _select_sources(only=args.only, exclude=args.exclude)
    except SourceSelectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_USAGE

    all_entries: list[FileEntry] = []
    for source in selected:
        if not source.should_run(today):
            print(f"[skip] {source.name}: should_run={False} for {today.isoformat()}")
            continue
        entries = _run_one_source(source, args=args, today=today)
        all_entries.extend(entries)

    anomalies = [e for e in all_entries if needs_notification(e)]
    if anomalies and not args.dry_run and not args.no_notify:
        emit_notifications(anomalies)

    return _exit_code(all_entries)


def _run_one_source(
    source: Source, *, args: argparse.Namespace, today: date
) -> list[FileEntry]:
    started = now_utc_iso()
    entries = list(source.snapshot(
        data_root=args.output_dir, today=today, dry_run=args.dry_run
    ))
    finished = now_utc_iso()
    _print_source_summary(source, entries, dry_run=args.dry_run)
    if not args.dry_run and entries:
        append_run(
            manifest_path(args.output_dir, source.name, "daily"),
            RunEntry(started_at=started, finished_at=finished, files=tuple(entries)),
        )
    return entries


# ---------------------------------------------------------------------------
# `list-sources` subcommand
# ---------------------------------------------------------------------------


def _list_sources(*, today: date) -> int:
    if not REGISTRY:
        print("(no sources registered)")
        return EXIT_OK
    width = max(len(name) for name in REGISTRY)
    for name, source in sorted(REGISTRY.items()):
        marker = "yes" if source.should_run(today) else "no "
        print(f"{name:<{width}}  should_run({today.isoformat()})={marker}  {source.display_name}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Source selection
# ---------------------------------------------------------------------------


class SourceSelectionError(ValueError):
    """Raised when --only / --exclude name a source that isn't registered."""


def _select_sources(*, only: list[str] | None, exclude: list[str] | None) -> list[Source]:
    """Resolve --only / --exclude into a concrete ordered list of sources.

    Validation rules:
        - Every name in `only` and `exclude` must be a registered source. A typo
          is a hard error, not a silent skip.
        - --only and --exclude cannot be combined; argparse enforces this too.
        - Order follows REGISTRY's insertion order (Python dicts preserve it),
          so manifests and notifications come out in a stable sequence.
    """
    if only and exclude:
        raise SourceSelectionError("--only and --exclude are mutually exclusive")

    known = set(REGISTRY)
    if only:
        unknown = sorted(set(only) - known)
        if unknown:
            raise SourceSelectionError(
                f"unknown source(s): {', '.join(unknown)}. registered: {', '.join(sorted(known))}"
            )
        wanted = set(only)
    elif exclude:
        unknown = sorted(set(exclude) - known)
        if unknown:
            raise SourceSelectionError(
                f"unknown source(s): {', '.join(unknown)}. registered: {', '.join(sorted(known))}"
            )
        wanted = known - set(exclude)
    else:
        wanted = known
    return [REGISTRY[name] for name in REGISTRY if name in wanted]


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="us-markets-timemachine",
        description="Daily snapshot worker for vanishing US markets data.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    daily = sub.add_parser("daily", help="Snapshot one or more registered sources.")
    daily.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Where to write captured files and manifests (default: ./data).",
    )
    daily.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate but do not write files or manifest.",
    )
    daily.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress Telegram + GitHub-issue alerts (still prints to stdout).",
    )
    selection = daily.add_mutually_exclusive_group()
    selection.add_argument(
        "--only",
        type=_csv_list,
        default=None,
        metavar="NAME[,NAME...]",
        help="Run only the named source(s). Comma-separated.",
    )
    selection.add_argument(
        "--exclude",
        type=_csv_list,
        default=None,
        metavar="NAME[,NAME...]",
        help="Run every source EXCEPT the named one(s). Comma-separated.",
    )

    sub.add_parser("list-sources", help="List registered sources and their should_run status.")

    return parser.parse_args(argv)


def _csv_list(s: str) -> list[str]:
    return [item.strip() for item in s.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_source_summary(
    source: Source, entries: Iterable[FileEntry], *, dry_run: bool
) -> None:
    entries = list(entries)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}[{source.name}] {counts}")
    for e in entries:
        marker = {
            "ok": "OK   ",
            "schema_drift": "DRIFT",
            "discovered": "FOUND",
            "invalid": "FAIL ",
            "missing": "MISS ",
        }.get(e.status, "?????")
        suffix = f" reason={e.reason}" if e.reason else ""
        print(f"{prefix}  [{marker}] {e.name:>40} rows={e.row_count}{suffix}")


def _exit_code(entries: list[FileEntry]) -> int:
    bad = {"invalid", "missing"}
    return EXIT_ANOMALY if any(e.status in bad for e in entries) else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
