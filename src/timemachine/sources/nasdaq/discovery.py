"""Discovery — spec section 4.4 + interview answers (auto-stage compromise).

After capture + mirror, list NASDAQ's SymDir/ index via FTP and diff against
(declared captured set + IGNORED_FILES) for files, and against
(MIRRORED_ARCHIVES + IGNORED_ARCHIVES) for subdirectories.

For each unknown FILE found upstream:
    - auto-fetch + permissive-validate
    - store under `data/nasdaq/_discovered/<filename>/<YYYY>/<YYYY-MM-DD>.gz`
      (NEVER under the canonical path; promotion to canonical requires a human
      PR per spec section 4.4)

For each unknown DIRECTORY: flag but DO NOT auto-traverse. Auto-traversing
unknown directories could trigger thousands of fetches; humans decide whether
to add the directory to MIRRORED_ARCHIVES or to IGNORED_ARCHIVES.

Discovery entries land in the daily manifest with status "discovered" so
they are trivially filterable (`jq '.runs[].files[] | select(.status ==
"discovered")'`).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from ftplib import FTP
from pathlib import Path

from timemachine.dates import et_today
from timemachine.http import FetchError, fetch
from timemachine.io import sha256_hex, write_gz
from timemachine.manifest import FileEntry
from timemachine.paths import discovered_path
from timemachine.sources.nasdaq.config import (
    CAPTURED_FILES,
    IGNORED_ARCHIVES,
    IGNORED_FILES,
    MIRRORED_ARCHIVES,
)
from timemachine.sources.nasdaq.validate import validate_simple

SOURCE = "nasdaq"

FTP_HOST = "ftp.nasdaqtrader.com"
SYMDIR_FTP_DIR = "/SymbolDirectory"
SYMDIR_HTTPS_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir"
DEFAULT_PAUSE_SECONDS = 0.05


@dataclass(frozen=True)
class SymDirEntry:
    name: str
    is_directory: bool


Lister = Callable[[], list[SymDirEntry]]
Fetcher = Callable[[str], bytes]


def run_discovery(
    *,
    data_root: Path,
    today: date | None = None,
    lister: Lister | None = None,
    fetcher: Fetcher | None = None,
    dry_run: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
) -> list[FileEntry]:
    list_fn: Lister = lister if lister is not None else ftp_list_symdir
    fetch_fn: Fetcher = fetcher if fetcher is not None else fetch
    d = today if today is not None else et_today()

    try:
        upstream = list_fn()
    except Exception as e:
        return [_listing_failure_entry(e)]

    captured_names = {f.name for f in CAPTURED_FILES}
    known_archives = set(MIRRORED_ARCHIVES) | IGNORED_ARCHIVES

    entries: list[FileEntry] = []
    for item in upstream:
        if not item.name:
            continue
        if item.is_directory:
            if item.name in known_archives:
                continue
            entries.append(_unknown_directory_entry(item.name))
            continue
        # File
        if item.name in captured_names or item.name in IGNORED_FILES:
            continue
        entries.append(
            _handle_unknown_file(
                item.name,
                data_root=data_root,
                today=d,
                fetcher=fetch_fn,
                dry_run=dry_run,
            )
        )
        sleep(pause_seconds)

    return entries


def _handle_unknown_file(
    name: str,
    *,
    data_root: Path,
    today: date,
    fetcher: Fetcher,
    dry_run: bool,
) -> FileEntry:
    url = f"{SYMDIR_HTTPS_BASE}/{name}"
    try:
        content = fetcher(url)
    except FetchError as e:
        return FileEntry(
            name=f"discovery:{name}",
            status="missing",
            stored_path=None,
            sha256=None,
            row_count=0,
            file_creation_time=None,
            reason=f"discovery_fetch_failed: {e}",
            source=SOURCE,
        )

    result = validate_simple(content, min_bytes=1)
    sha = sha256_hex(content)

    if result.status == "invalid":
        return FileEntry(
            name=f"discovery:{name}",
            status="invalid",
            stored_path=None,
            sha256=sha,
            row_count=0,
            file_creation_time=None,
            reason=f"discovery validation failed: {result.reason}",
            source=SOURCE,
        )

    target = discovered_path(data_root, SOURCE, name, today)
    if target.exists():
        return FileEntry(
            name=f"discovery:{name}",
            status="discovered",
            stored_path=_repo_relative(target, data_root),
            sha256=sha,
            row_count=result.row_count,
            file_creation_time=None,
            reason="already staged for today",
            source=SOURCE,
        )

    if not dry_run:
        write_gz(target, content)

    return FileEntry(
        name=f"discovery:{name}",
        status="discovered",
        stored_path=_repo_relative(target, data_root),
        sha256=sha,
        row_count=result.row_count,
        file_creation_time=None,
        reason="unknown file auto-staged; human curation required",
        source=SOURCE,
    )


def _unknown_directory_entry(name: str) -> FileEntry:
    return FileEntry(
        name=f"discovery:{name}/",
        status="discovered",
        stored_path=None,
        sha256=None,
        row_count=0,
        file_creation_time=None,
        reason="unknown subdirectory upstream (not auto-traversed)",
        source=SOURCE,
    )


def _listing_failure_entry(exc: Exception) -> FileEntry:
    return FileEntry(
        name="discovery:<listing>",
        status="missing",
        stored_path=None,
        sha256=None,
        row_count=0,
        file_creation_time=None,
        reason=f"ftp_list_failed: {exc}",
        source=SOURCE,
    )


def _repo_relative(target: Path, data_root: Path) -> str:
    repo_root = data_root.parent
    try:
        return str(target.relative_to(repo_root))
    except ValueError:
        return str(target)


def ftp_list_symdir(*, timeout: float = 30.0) -> list[SymDirEntry]:
    """List SymDir/ via FTP. DOS-style LIST output marks directories with <DIR>."""
    lines: list[str] = []
    with FTP(FTP_HOST, timeout=timeout) as conn:
        conn.login()  # anonymous
        conn.cwd(SYMDIR_FTP_DIR)
        conn.retrlines("LIST", lines.append)
    return [_parse_dos_line(line) for line in lines if line.strip()]


def _parse_dos_line(line: str) -> SymDirEntry:
    parts = line.split(maxsplit=3)
    if len(parts) < 4:
        return SymDirEntry(name="", is_directory=False)
    return SymDirEntry(name=parts[3], is_directory="<DIR>" in line)
