"""Content validation rules — spec section 4.3 (NASDAQ-specific).

A fetched file passes only if it is not an HTML error page, is above a
per-file minimum size, has the declared header (or has a new trailing column
appended to it — that flags `schema_drift`, not rejection), uses the declared
delimiter, has the expected trailer where one is declared, and has a row count
above a per-file sanity floor.

Anything that fails is `invalid` and must be parked in
`data/nasdaq/_rejected/` — never stored under a real dated path.

Other sources (e.g. EDGAR, with JSON payloads) ship their own validators in
`sources/<name>/validate.py`.
"""

from dataclasses import dataclass
from typing import Literal

from timemachine.sources.nasdaq.config import CapturedFile

Status = Literal["ok", "invalid", "schema_drift"]


@dataclass(frozen=True)
class ValidationResult:
    status: Status
    reason: str | None
    row_count: int
    file_creation_time: str | None


def validate(content: bytes, spec: CapturedFile) -> ValidationResult:
    # 1. Reject HTML error pages outright (NASDAQ redirects dead files to HTML).
    head = content[:512].decode("utf-8", errors="replace").lower().lstrip()
    if head.startswith("<!doctype") or head.startswith("<html") or "<html" in head:
        return ValidationResult("invalid", "html_response", 0, None)

    # 2. Minimum size.
    if len(content) < spec.min_bytes:
        return ValidationResult(
            "invalid", f"below_min_size: {len(content)} < {spec.min_bytes}", 0, None
        )

    # 3. Decode as UTF-8.
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        return ValidationResult("invalid", f"utf8_decode_failed: {e}", 0, None)

    lines = text.splitlines()
    if not lines:
        return ValidationResult("invalid", "empty_file", 0, None)

    # 4. Header match — lenient on a new trailing column (flagged, not rejected).
    header = lines[0]
    schema_drift_reason: str | None = None
    if header != spec.expected_header:
        prefix = spec.expected_header + spec.delimiter
        if header.startswith(prefix):
            new_columns = header[len(spec.expected_header) :]
            schema_drift_reason = f"new_trailing_column: {new_columns}"
        else:
            return ValidationResult("invalid", "header_mismatch", 0, None)

    # 5. Delimiter sanity — at least one data line must contain the delimiter.
    if len(lines) >= 2 and spec.delimiter not in lines[1]:
        return ValidationResult(
            "invalid", f"delimiter_missing: expected '{spec.delimiter}' in data rows", 0, None
        )

    # 6. Trailer.
    file_creation_time: str | None = None
    if spec.trailer_pattern is not None:
        trailer_idx: int | None = None
        for i in range(len(lines) - 1, max(-1, len(lines) - 6), -1):
            if spec.trailer_pattern.match(lines[i]):
                trailer_idx = i
                file_creation_time = lines[i]
                break
        if trailer_idx is None:
            return ValidationResult("invalid", "trailer_missing", 0, None)
        row_count = trailer_idx - 1  # exclude header AND trailer
    else:
        row_count = len(lines) - 1  # exclude header only

    # 7. Row-count floor.
    if row_count < spec.min_rows:
        return ValidationResult(
            "invalid",
            f"below_min_rows: {row_count} < {spec.min_rows}",
            row_count,
            file_creation_time,
        )

    if schema_drift_reason is not None:
        return ValidationResult("schema_drift", schema_drift_reason, row_count, file_creation_time)

    return ValidationResult("ok", None, row_count, file_creation_time)


def validate_simple(content: bytes, *, min_bytes: int = 1) -> ValidationResult:
    """Permissive validation for mirrored archive files.

    Mirrored files (regsho, shorthalts, regnms) have varied formats per
    exchange and per era — the per-file header / delimiter / trailer checks
    used for the captured set don't generalize. Mirror only enforces:
        - not an HTML error page
        - above a (very small) minimum size

    Per-file row counting is left to consumers reading the data later.
    """
    head = content[:512].decode("utf-8", errors="replace").lower().lstrip()
    if head.startswith("<!doctype") or head.startswith("<html") or "<html" in head:
        return ValidationResult("invalid", "html_response", 0, None)
    if len(content) < min_bytes:
        return ValidationResult(
            "invalid", f"below_min_size: {len(content)} < {min_bytes}", 0, None
        )
    # Row count = newline-separated lines (rough). Not strictly enforced.
    row_count = content.count(b"\n")
    return ValidationResult("ok", None, row_count, None)
