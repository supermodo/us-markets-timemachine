"""Mirror-delta job — spec §4.2.

For each archive in ARCHIVES:
    1. FTP-list the upstream directory (only way to enumerate; HTTPS LIST
       returns 403 from nasdaqtrader.com).
    2. For each filename matching the archive's pattern, parse the embedded
       YYYYMMDD into a date.
    3. Compute the local target path; skip if already held (idempotent +
       resumable — spec §4.2).
    4. HTTPS-fetch (faster, more firewall-friendly than FTP RETR), validate
       permissively, store under `data/nasdaq/<archive>/<YYYY>/<original-filename>.gz`.

First invocation runs the full historical backfill (regsho 2005→, shorthalts
2011→, regnms 2007→ — combined ~130 MB, ~10k files). Subsequent invocations
pick up only days NASDAQ has added since.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from ftplib import FTP
from pathlib import Path

from timemachine.http import FetchError, fetch
from timemachine.io import sha256_hex, write_gz
from timemachine.manifest import FileEntry
from timemachine.paths import mirrored_path
from timemachine.sources.nasdaq.validate import validate_simple

SOURCE = "nasdaq"

FTP_HOST = "ftp.nasdaqtrader.com"
FTP_BASE_DIR = "/SymbolDirectory"
HTTPS_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir"

# Minimum byte floor for mirror files. Note: shorthalts20110225.txt = 19 bytes
# (legit single-line file), so this is intentionally permissive.
MIRROR_MIN_BYTES = 10

# Polite pause between individual file fetches during backfill.
DEFAULT_FETCH_PAUSE_SECONDS = 0.05


@dataclass(frozen=True)
class ArchiveSpec:
    name: str
    filename_pattern: re.Pattern[str]  # group(1) must be YYYYMMDD


ARCHIVES: tuple[ArchiveSpec, ...] = (
    ArchiveSpec("regsho", re.compile(r"^nasdaqth(\d{8})(?:original)?\.txt$")),
    ArchiveSpec("shorthalts", re.compile(r"^shorthalts(\d{8})\.txt$")),
    ArchiveSpec("regnms", re.compile(r"^regnmspilot(\d{8})\.txt$")),
)


Lister = Callable[[str], list[str]]
Fetcher = Callable[[str], bytes]


def run_mirror(
    *,
    data_root: Path,
    lister: Lister | None = None,
    fetcher: Fetcher | None = None,
    dry_run: bool = False,
    max_per_archive: int | None = None,
    fetch_pause_seconds: float = DEFAULT_FETCH_PAUSE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[FileEntry]:
    list_fn: Lister = lister if lister is not None else ftp_list_archive
    fetch_fn: Fetcher = fetcher if fetcher is not None else fetch
    entries: list[FileEntry] = []
    for archive in ARCHIVES:
        try:
            filenames = list_fn(archive.name)
        except Exception as e:  # broad: ftplib raises many concrete types
            entries.append(_listing_failure_entry(archive, e))
            continue
        entries.extend(
            _mirror_one(
                archive,
                filenames,
                data_root=data_root,
                fetcher=fetch_fn,
                dry_run=dry_run,
                max_files=max_per_archive,
                pause=fetch_pause_seconds,
                sleep=sleep,
            )
        )
    return entries


def _mirror_one(
    archive: ArchiveSpec,
    filenames: list[str],
    *,
    data_root: Path,
    fetcher: Fetcher,
    dry_run: bool,
    max_files: int | None,
    pause: float,
    sleep: Callable[[float], None],
) -> list[FileEntry]:
    out: list[FileEntry] = []
    new_count = 0
    for fname in filenames:
        m = archive.filename_pattern.match(fname)
        if m is None:
            continue  # filename doesn't match — silently skipped (e.g. "Reg SHO Security Summary Jan 2 2007.txt")
        try:
            d = _parse_yyyymmdd(m.group(1))
        except ValueError:
            continue

        target = mirrored_path(data_root, SOURCE, archive.name, fname, d)
        if target.exists():
            continue  # already held — idempotent skip

        if max_files is not None and new_count >= max_files:
            break

        url = f"{HTTPS_BASE}/{archive.name}/{fname}"
        try:
            content = fetcher(url)
        except FetchError as e:
            out.append(
                FileEntry(
                    name=f"{archive.name}/{fname}",
                    status="missing",
                    stored_path=None,
                    sha256=None,
                    row_count=0,
                    file_creation_time=None,
                    reason=str(e),
                    source=SOURCE,
                )
            )
            new_count += 1
            sleep(pause)
            continue

        result = validate_simple(content, min_bytes=MIRROR_MIN_BYTES)
        sha = sha256_hex(content)

        if result.status == "invalid":
            # Mirror invalids do NOT go to _rejected/ — they go nowhere on disk;
            # the failure is recorded in the manifest. Reason: mirror files come
            # from a directory listing and a transient invalid response shouldn't
            # leave a persistent artifact at the upstream-filename path.
            out.append(
                FileEntry(
                    name=f"{archive.name}/{fname}",
                    status="invalid",
                    stored_path=None,
                    sha256=sha,
                    row_count=0,
                    file_creation_time=None,
                    reason=result.reason,
                    source=SOURCE,
                )
            )
        else:
            if not dry_run:
                write_gz(target, content)
            out.append(
                FileEntry(
                    name=f"{archive.name}/{fname}",
                    status=result.status,
                    stored_path=_repo_relative(target, data_root),
                    sha256=sha,
                    row_count=result.row_count,
                    file_creation_time=None,
                    reason=None,
                    source=SOURCE,
                )
            )

        new_count += 1
        sleep(pause)

    return out


def _listing_failure_entry(archive: ArchiveSpec, exc: Exception) -> FileEntry:
    return FileEntry(
        name=f"{archive.name}/<listing>",
        status="missing",
        stored_path=None,
        sha256=None,
        row_count=0,
        file_creation_time=None,
        reason=f"ftp_list_failed: {exc}",
        source=SOURCE,
    )


def _parse_yyyymmdd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _repo_relative(target: Path, data_root: Path) -> str:
    repo_root = data_root.parent
    try:
        return str(target.relative_to(repo_root))
    except ValueError:
        return str(target)


def ftp_list_archive(archive_name: str, *, timeout: float = 30.0) -> list[str]:
    """Return the list of filenames in NASDAQ's <archive> FTP directory.

    Uses anonymous FTP. Output of LIST is DOS-style:
        MM-DD-YY  HH:MMam/pm   <BYTES> <FILENAME>
    where filename can contain spaces (split with maxsplit=3).
    """
    lines: list[str] = []
    with FTP(FTP_HOST, timeout=timeout) as ftp_conn:
        ftp_conn.login()  # anonymous
        ftp_conn.cwd(f"{FTP_BASE_DIR}/{archive_name}")
        ftp_conn.retrlines("LIST", lines.append)
    return [_filename_from_dos_listing(line) for line in lines if line.strip()]


def _filename_from_dos_listing(line: str) -> str:
    parts = line.split(maxsplit=3)
    return parts[3] if len(parts) == 4 else ""
