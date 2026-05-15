import json
from pathlib import Path

import pytest

from timemachine.manifest import FileEntry, RunEntry, append_run, read_runs


def _run(*, started: str, finished: str, files: tuple[FileEntry, ...] = ()) -> RunEntry:
    return RunEntry(started_at=started, finished_at=finished, files=files)


def test_append_to_new_file_creates_runs_list(tmp_path: Path):
    manifest = tmp_path / "manifest-daily.json"
    file_entry = FileEntry(
        name="nasdaqtraded.txt",
        status="ok",
        stored_path="data/nasdaqtraded/2026/2026-05-14.txt.gz",
        sha256="abc123",
        row_count=12634,
        file_creation_time="File Creation Time: 0514202615:42|||||",
        reason=None,
    )
    run = _run(
        started="2026-05-14T20:00:00Z",
        finished="2026-05-14T20:00:23Z",
        files=(file_entry,),
    )

    append_run(manifest, run)

    data = json.loads(manifest.read_text())
    assert list(data.keys()) == ["runs"]
    assert len(data["runs"]) == 1
    assert data["runs"][0]["started_at"] == "2026-05-14T20:00:00Z"
    assert data["runs"][0]["files"][0]["name"] == "nasdaqtraded.txt"
    assert data["runs"][0]["files"][0]["status"] == "ok"


def test_append_run_is_appendonly(tmp_path: Path):
    manifest = tmp_path / "manifest-daily.json"
    append_run(manifest, _run(started="2026-05-14T20:00:00Z", finished="2026-05-14T20:00:23Z"))
    append_run(manifest, _run(started="2026-05-15T20:00:00Z", finished="2026-05-15T20:00:17Z"))
    append_run(manifest, _run(started="2026-05-16T20:00:00Z", finished="2026-05-16T20:00:19Z"))

    runs = read_runs(manifest)
    assert [r["started_at"] for r in runs] == [
        "2026-05-14T20:00:00Z",
        "2026-05-15T20:00:00Z",
        "2026-05-16T20:00:00Z",
    ]


def test_malformed_manifest_raises(tmp_path: Path):
    manifest = tmp_path / "manifest-daily.json"
    manifest.write_text('{"not_runs": []}')
    with pytest.raises(ValueError):
        read_runs(manifest)


def test_read_runs_on_missing_file_returns_empty(tmp_path: Path):
    assert read_runs(tmp_path / "does-not-exist.json") == []


def test_atomic_write_no_partial_file(tmp_path: Path):
    # After append, only the final manifest should exist — no .tmp left behind.
    manifest = tmp_path / "manifest-daily.json"
    append_run(manifest, _run(started="2026-05-14T20:00:00Z", finished="2026-05-14T20:00:23Z"))
    assert manifest.exists()
    assert not (tmp_path / "manifest-daily.json.tmp").exists()
