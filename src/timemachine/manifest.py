"""Append-only manifest writer — spec section 3.5.

Every run's outcome is appended to a per-source manifest at
`data/<source>/manifest-<kind>.json`. Prior runs are never overwritten; the
manifest is its own audit log.

Schema:
    {"runs": [
        {
            "started_at": "2026-05-14T20:00:00Z",
            "finished_at": "2026-05-14T20:00:23Z",
            "files": [
                {"source": "nasdaq", "name": "nasdaqtraded.txt", "status": "ok",
                 "stored_path": "data/nasdaq/nasdaqtraded/2026/2026-05-14.txt.gz",
                 "sha256": "...", "row_count": 12634,
                 "file_creation_time": "File Creation Time: 0514202615:42|||||",
                 "reason": null},
                ...
            ]
        },
        ...
    ]}

The `source` field on every file entry is intentionally redundant with the
manifest's filesystem location — this lets cross-source tooling identify
provenance from a single entry without needing the file's path context.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileEntry:
    name: str
    status: str  # "ok" | "invalid" | "missing" | "schema_drift" | "discovered"
    stored_path: str | None
    sha256: str | None
    row_count: int
    file_creation_time: str | None
    reason: str | None
    source: str = ""  # populated by every source from Phase 3 onward


@dataclass(frozen=True)
class RunEntry:
    started_at: str  # ISO 8601 UTC, e.g. "2026-05-14T20:00:00Z"
    finished_at: str
    files: tuple[FileEntry, ...]


def append_run(manifest_path: Path, run: RunEntry) -> None:
    runs = _load_runs(manifest_path)
    runs.append(_run_to_dict(run))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(json.dumps({"runs": runs}, indent=2))
    tmp.replace(manifest_path)  # atomic on POSIX


def read_runs(manifest_path: Path) -> list[dict]:
    return _load_runs(manifest_path)


def _load_runs(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict) or "runs" not in data or not isinstance(data["runs"], list):
        raise ValueError(f"malformed manifest at {manifest_path}: expected {{'runs': [...]}}")
    return data["runs"]


def _run_to_dict(run: RunEntry) -> dict:
    return {
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "files": [asdict(f) for f in run.files],
    }
