"""Deterministic gzip write + sha256 helpers.

Write is atomic via tmp + rename so a crash mid-write never leaves a partial
file at the canonical path. Gzip is deterministic (mtime=0, no filename
header) so the same input bytes always produce the same blob — enabling git's
content-aware delta-dedup across runs.
"""

import gzip
import hashlib
from pathlib import Path


def write_gz(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(data, mtime=0))
    tmp.replace(path)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
