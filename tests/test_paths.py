import re
from datetime import date
from pathlib import Path

from timemachine.paths import (
    captured_path,
    discovered_path,
    manifest_path,
    mirrored_path,
    rejected_path,
    source_root,
)
from timemachine.sources.nasdaq.config import CapturedFile


def _spec(name: str = "nasdaqtraded.txt") -> CapturedFile:
    return CapturedFile(
        name=name,
        delimiter="|",
        expected_header="header",
        min_bytes=1,
        min_rows=0,
        trailer_pattern=re.compile(r"^trailer"),
    )


def test_source_root_is_data_root_plus_source():
    assert source_root(Path("data"), "nasdaq") == Path("data/nasdaq")
    assert source_root(Path("data"), "edgar") == Path("data/edgar")


def test_captured_path_is_namespaced_by_source_for_txt_file():
    p = captured_path(Path("data"), "nasdaq", _spec("nasdaqtraded.txt"), date(2026, 5, 14))
    assert p == Path("data/nasdaq/nasdaqtraded/2026/2026-05-14.txt.gz")


def test_captured_path_is_namespaced_by_source_for_csv_file():
    p = captured_path(Path("data"), "nasdaq", _spec("foo.csv"), date(2026, 5, 14))
    assert p == Path("data/nasdaq/foo/2026/2026-05-14.gz")


def test_rejected_path_groups_by_source_then_date_then_filename():
    p = rejected_path(Path("data"), "nasdaq", "nasdaqtraded.txt", date(2026, 5, 14))
    assert p == Path("data/nasdaq/_rejected/2026/2026-05-14/nasdaqtraded.txt.gz")


def test_discovered_path_groups_by_source_then_filename_then_year_then_date():
    p = discovered_path(Path("data"), "nasdaq", "mysteryfile.txt", date(2026, 5, 14))
    assert p == Path("data/nasdaq/_discovered/mysteryfile.txt/2026/2026-05-14.gz")


def test_mirrored_path_preserves_original_filename_under_source_namespace():
    p = mirrored_path(Path("data"), "nasdaq", "regsho", "nasdaqth20260514.txt", date(2026, 5, 14))
    assert p == Path("data/nasdaq/regsho/2026/nasdaqth20260514.txt.gz")


def test_manifest_path_is_per_source_per_kind():
    assert manifest_path(Path("data"), "nasdaq", "daily") == Path("data/nasdaq/manifest-daily.json")
    assert manifest_path(Path("data"), "nasdaq", "mirror") == Path("data/nasdaq/manifest-mirror.json")
    assert manifest_path(Path("data"), "edgar", "daily") == Path("data/edgar/manifest-daily.json")
