"""Daily capture job — spec section 4.1.

For each declared file in CAPTURED_FILES:
  fetch  →  validate  →  on pass: store at dated path; on fail: park in _rejected/.
  on fetch error: record `missing` and continue (one file never crashes another).

Returns a list of FileEntry; the caller (daily.py / source.py) writes the manifest.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path

from timemachine.dates import et_today
from timemachine.http import FetchError, fetch
from timemachine.io import sha256_hex, write_gz
from timemachine.manifest import FileEntry
from timemachine.paths import captured_path, rejected_path
from timemachine.sources.nasdaq.config import CAPTURED_FILES, CapturedFile
from timemachine.sources.nasdaq.validate import validate

Fetcher = Callable[[str], bytes]

SOURCE = "nasdaq"


def run_capture(
    *,
    data_root: Path,
    fetcher: Fetcher | None = None,
    today: date | None = None,
    dry_run: bool = False,
    specs: tuple[CapturedFile, ...] | None = None,
) -> list[FileEntry]:
    f: Fetcher = fetcher if fetcher is not None else fetch
    d = today if today is not None else et_today()
    file_specs = specs if specs is not None else CAPTURED_FILES
    return [_capture_one(spec, data_root=data_root, today=d, fetcher=f, dry_run=dry_run) for spec in file_specs]


def _capture_one(
    spec: CapturedFile,
    *,
    data_root: Path,
    today: date,
    fetcher: Fetcher,
    dry_run: bool,
) -> FileEntry:
    try:
        content = fetcher(spec.url)
    except FetchError as e:
        return FileEntry(
            name=spec.name,
            status="missing",
            stored_path=None,
            sha256=None,
            row_count=0,
            file_creation_time=None,
            reason=str(e),
            source=SOURCE,
        )

    result = validate(content, spec)
    sha = sha256_hex(content)

    if result.status == "invalid":
        target = rejected_path(data_root, SOURCE, spec.name, today)
        if not dry_run:
            write_gz(target, content)
        return FileEntry(
            name=spec.name,
            status="invalid",
            stored_path=_repo_relative(target, data_root),
            sha256=sha,
            row_count=result.row_count,
            file_creation_time=result.file_creation_time,
            reason=result.reason,
            source=SOURCE,
        )

    target = captured_path(data_root, SOURCE, spec, today)
    if target.exists():
        return FileEntry(
            name=spec.name,
            status=result.status,
            stored_path=_repo_relative(target, data_root),
            sha256=sha,
            row_count=result.row_count,
            file_creation_time=result.file_creation_time,
            reason="already_existed_not_overwritten",
            source=SOURCE,
        )

    if not dry_run:
        write_gz(target, content)

    return FileEntry(
        name=spec.name,
        status=result.status,
        stored_path=_repo_relative(target, data_root),
        sha256=sha,
        row_count=result.row_count,
        file_creation_time=result.file_creation_time,
        reason=result.reason,
        source=SOURCE,
    )


def _repo_relative(target: Path, data_root: Path) -> str:
    """Return a stable, repo-relative path string for the manifest.

    `data_root` is typically `<repo>/data`. Manifest paths read better as
    `data/nasdaq/foo/2026/...` than as absolute paths.
    """
    repo_root = data_root.parent
    try:
        return str(target.relative_to(repo_root))
    except ValueError:
        return str(target)
