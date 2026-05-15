"""Tests for the multi-source CLI dispatch and selection logic.

Network-free: every source in REGISTRY is monkeypatched to a fake that records
calls and returns canned FileEntry rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from timemachine import cli
from timemachine.manifest import FileEntry


@dataclass
class FakeSource:
    name: str
    display_name: str = "fake"
    should_run_value: bool = True
    canned_entries: tuple[FileEntry, ...] = ()
    snapshot_calls: list[dict] = field(default_factory=list)

    def should_run(self, today: date) -> bool:
        del today
        return self.should_run_value

    def snapshot(
        self, *, data_root: Path, today: date, dry_run: bool = False
    ) -> Iterable[FileEntry]:
        self.snapshot_calls.append({"data_root": data_root, "today": today, "dry_run": dry_run})
        return self.canned_entries


def _ok_entry(source: str, name: str = "thing.txt") -> FileEntry:
    return FileEntry(
        name=name,
        status="ok",
        stored_path=f"data/{source}/{name}/2026/2026-05-15.gz",
        sha256="abc",
        row_count=42,
        file_creation_time=None,
        reason=None,
        source=source,
    )


def _bad_entry(source: str, name: str = "broken.txt") -> FileEntry:
    return FileEntry(
        name=name,
        status="invalid",
        stored_path=None,
        sha256=None,
        row_count=0,
        file_creation_time=None,
        reason="header_mismatch",
        source=source,
    )


@pytest.fixture
def fake_registry(monkeypatch):
    nasdaq = FakeSource(name="nasdaq", canned_entries=(_ok_entry("nasdaq"),))
    edgar = FakeSource(name="edgar", canned_entries=(_ok_entry("edgar"),))
    monkeypatch.setattr(cli, "REGISTRY", {"nasdaq": nasdaq, "edgar": edgar})
    return {"nasdaq": nasdaq, "edgar": edgar}


def test_list_sources_prints_each_registered_source(fake_registry, capsys):
    rc = cli.main(["list-sources"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "nasdaq" in out
    assert "edgar" in out


def test_daily_with_no_selection_runs_every_source(fake_registry, tmp_path):
    rc = cli.main(["daily", "--output-dir", str(tmp_path / "data"), "--no-notify"])
    assert rc == 0
    assert len(fake_registry["nasdaq"].snapshot_calls) == 1
    assert len(fake_registry["edgar"].snapshot_calls) == 1


def test_daily_only_runs_named_sources(fake_registry, tmp_path):
    rc = cli.main(
        ["daily", "--only", "edgar", "--output-dir", str(tmp_path / "data"), "--no-notify"]
    )
    assert rc == 0
    assert fake_registry["nasdaq"].snapshot_calls == []
    assert len(fake_registry["edgar"].snapshot_calls) == 1


def test_daily_exclude_skips_named_source(fake_registry, tmp_path):
    rc = cli.main(
        ["daily", "--exclude", "edgar", "--output-dir", str(tmp_path / "data"), "--no-notify"]
    )
    assert rc == 0
    assert len(fake_registry["nasdaq"].snapshot_calls) == 1
    assert fake_registry["edgar"].snapshot_calls == []


def test_daily_unknown_source_in_only_is_a_usage_error(fake_registry, tmp_path, capsys):
    rc = cli.main(
        ["daily", "--only", "nadsaq", "--output-dir", str(tmp_path / "data"), "--no-notify"]
    )
    assert rc == cli.EXIT_BAD_USAGE
    err = capsys.readouterr().err
    assert "unknown source" in err
    assert "nadsaq" in err


def test_daily_skips_sources_whose_should_run_returns_false(fake_registry, tmp_path):
    fake_registry["edgar"].should_run_value = False
    rc = cli.main(["daily", "--output-dir", str(tmp_path / "data"), "--no-notify"])
    assert rc == 0
    assert len(fake_registry["nasdaq"].snapshot_calls) == 1
    assert fake_registry["edgar"].snapshot_calls == []


def test_daily_anomaly_returns_exit_code_1(fake_registry, tmp_path):
    fake_registry["nasdaq"].canned_entries = (_bad_entry("nasdaq"),)
    rc = cli.main(["daily", "--output-dir", str(tmp_path / "data"), "--no-notify"])
    assert rc == 1


def test_daily_writes_per_source_manifest(fake_registry, tmp_path):
    out = tmp_path / "data"
    cli.main(["daily", "--output-dir", str(out), "--no-notify"])
    nasdaq_manifest = out / "nasdaq" / "manifest-daily.json"
    edgar_manifest = out / "edgar" / "manifest-daily.json"
    assert nasdaq_manifest.exists()
    assert edgar_manifest.exists()
    nasdaq_data = json.loads(nasdaq_manifest.read_text())
    assert len(nasdaq_data["runs"]) == 1
    assert nasdaq_data["runs"][0]["files"][0]["source"] == "nasdaq"


def test_dry_run_does_not_write_manifest(fake_registry, tmp_path):
    out = tmp_path / "data"
    cli.main(["daily", "--dry-run", "--output-dir", str(out), "--no-notify"])
    assert not (out / "nasdaq" / "manifest-daily.json").exists()
    assert fake_registry["nasdaq"].snapshot_calls[0]["dry_run"] is True
