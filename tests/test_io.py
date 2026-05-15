import gzip
from pathlib import Path

from timemachine.io import sha256_hex, write_gz


def test_write_gz_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "a" / "b" / "c.txt.gz"
    write_gz(target, b"hello")
    assert target.exists()
    assert gzip.decompress(target.read_bytes()) == b"hello"


def test_write_gz_is_deterministic(tmp_path: Path):
    # Same input twice must produce byte-identical gzip blobs (key git-dedup
    # property — see spec discussion of gzip -n).
    a = tmp_path / "a.gz"
    b = tmp_path / "b.gz"
    write_gz(a, b"some content for the archive")
    write_gz(b, b"some content for the archive")
    assert a.read_bytes() == b.read_bytes()


def test_write_gz_atomic_no_tmp_left_behind(tmp_path: Path):
    target = tmp_path / "out.gz"
    write_gz(target, b"payload")
    siblings = sorted(p.name for p in tmp_path.iterdir())
    assert siblings == ["out.gz"]


def test_sha256_hex_known_value():
    # sha256("hello") known constant
    assert sha256_hex(b"hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
