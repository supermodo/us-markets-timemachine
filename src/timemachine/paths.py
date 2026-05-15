"""Filesystem layout for the archive — spec section 3.4.

Every path is namespaced by `source` so each source's data, manifests, rejects,
and discoveries live in a fully self-contained subtree under `data/<source>/`.
This keeps each source's legal posture, lifecycle, and storage cleanly
separable (spec section 6).

Captured files (the daily-overwritten set):
    data/<source>/<dir_name>/<YYYY>/<YYYY-MM-DD>.txt.gz

Mirrored files (sources that publish their own dated archives):
    data/<source>/<archive>/<YYYY>/<original-dated-filename>.gz

Rejected fetches (failed validation — never stored under a real date):
    data/<source>/_rejected/<YYYY>/<YYYY-MM-DD>/<source-filename>.gz

Auto-discovered unknown files (not in the declared set, awaiting human curation):
    data/<source>/_discovered/<source-filename>/<YYYY>/<YYYY-MM-DD>.gz

Per-source append-only manifests:
    data/<source>/manifest-<kind>.json    (kind: daily | mirror | discovery | …)
"""

from datetime import date
from pathlib import Path
from typing import Protocol

from timemachine.dates import date_path_parts


class _CapturedFileLike(Protocol):
    """Duck-typed spec needed by `captured_path`. Any source's spec satisfies it."""

    name: str

    @property
    def dir_name(self) -> str: ...


def source_root(data_root: Path, source: str) -> Path:
    return data_root / source


def captured_path(data_root: Path, source: str, spec: _CapturedFileLike, d: date) -> Path:
    year, full = date_path_parts(d)
    ext = ".txt.gz" if spec.name.endswith(".txt") else ".gz"
    return source_root(data_root, source) / spec.dir_name / year / f"{full}{ext}"


def rejected_path(data_root: Path, source: str, source_filename: str, d: date) -> Path:
    year, full = date_path_parts(d)
    return source_root(data_root, source) / "_rejected" / year / full / f"{source_filename}.gz"


def discovered_path(data_root: Path, source: str, source_filename: str, d: date) -> Path:
    year, full = date_path_parts(d)
    return source_root(data_root, source) / "_discovered" / source_filename / year / f"{full}.gz"


def mirrored_path(
    data_root: Path, source: str, archive: str, original_filename: str, d: date
) -> Path:
    """Mirrored files keep their original upstream filename; we just append .gz."""
    year, _ = date_path_parts(d)
    return source_root(data_root, source) / archive / year / f"{original_filename}.gz"


def manifest_path(data_root: Path, source: str, kind: str) -> Path:
    """Per-source append-only manifest. `kind` is e.g. 'daily', 'mirror', 'discovery'."""
    return source_root(data_root, source) / f"manifest-{kind}.json"
