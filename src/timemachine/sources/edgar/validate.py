"""EDGAR-specific JSON validators.

Each validator returns a `ValidationResult` mirroring the per-source pattern
NASDAQ uses, but tuned for JSON shapes:

    company_tickers.json          → object keyed by stringified ints,
                                     each value `{cik_str, ticker, title}`.
    company_tickers_exchange.json → `{"fields": [...], "data": [[...], ...]}`.

Schema-drift policy mirrors NASDAQ section 4.3: a *new* trailing field on the inner
records is logged as `schema_drift` (file is still stored faithfully); a
*missing* required field or a wholesale shape change is `invalid`.

`validate_html_or_short` is the small generic gate (HTML error page detection
+ minimum-size check) reused by both files before any JSON parsing happens —
SEC sometimes returns an HTML maintenance page instead of the JSON file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from timemachine.sources.edgar.config import EdgarFile

Status = Literal["ok", "invalid", "schema_drift"]

COMPANY_TICKERS_REQUIRED_FIELDS = frozenset({"cik_str", "ticker", "title"})
COMPANY_TICKERS_EXCHANGE_REQUIRED_FIELDS = frozenset({"cik", "name", "ticker", "exchange"})


@dataclass(frozen=True)
class ValidationResult:
    status: Status
    reason: str | None
    row_count: int


def validate_html_or_short(content: bytes, *, min_bytes: int) -> ValidationResult | None:
    """Return a failing ValidationResult if content is HTML or under min_bytes.

    Returns None if the bytes look plausible enough to attempt JSON parsing.
    """
    head = content[:512].decode("utf-8", errors="replace").lower().lstrip()
    if head.startswith("<!doctype") or head.startswith("<html") or "<html" in head:
        return ValidationResult("invalid", "html_response", 0)
    if len(content) < min_bytes:
        return ValidationResult(
            "invalid", f"below_min_size: {len(content)} < {min_bytes}", 0
        )
    return None


def validate_company_tickers(content: bytes, spec: EdgarFile) -> ValidationResult:
    if (early := validate_html_or_short(content, min_bytes=spec.min_bytes)) is not None:
        return early
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as e:
        return ValidationResult("invalid", f"json_decode_failed: {e}", 0)

    if not isinstance(payload, dict) or not payload:
        return ValidationResult("invalid", "expected_non_empty_object", 0)

    sample_key = next(iter(payload))
    sample = payload[sample_key]
    if not isinstance(sample, dict):
        return ValidationResult(
            "invalid", f"expected dict records, got {type(sample).__name__}", 0
        )

    sample_fields = set(sample)
    missing = COMPANY_TICKERS_REQUIRED_FIELDS - sample_fields
    if missing:
        return ValidationResult(
            "invalid", f"missing_required_fields: {sorted(missing)}", 0
        )

    record_count = len(payload)
    if record_count < spec.min_records:
        return ValidationResult(
            "invalid", f"below_min_records: {record_count} < {spec.min_records}", record_count
        )

    extras = sample_fields - COMPANY_TICKERS_REQUIRED_FIELDS
    if extras:
        return ValidationResult(
            "schema_drift", f"new_fields: {sorted(extras)}", record_count
        )
    return ValidationResult("ok", None, record_count)


def validate_company_tickers_exchange(content: bytes, spec: EdgarFile) -> ValidationResult:
    if (early := validate_html_or_short(content, min_bytes=spec.min_bytes)) is not None:
        return early
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as e:
        return ValidationResult("invalid", f"json_decode_failed: {e}", 0)

    if not isinstance(payload, dict):
        return ValidationResult("invalid", "expected_object_at_top_level", 0)
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        return ValidationResult("invalid", "expected_fields_and_data_arrays", 0)

    field_set = set(fields)
    missing = COMPANY_TICKERS_EXCHANGE_REQUIRED_FIELDS - field_set
    if missing:
        return ValidationResult(
            "invalid", f"missing_required_fields: {sorted(missing)}", 0
        )

    if len(data) < spec.min_records:
        return ValidationResult(
            "invalid", f"below_min_records: {len(data)} < {spec.min_records}", len(data)
        )

    width = len(fields)
    bad_row = next((i for i, row in enumerate(data) if not isinstance(row, list) or len(row) != width), None)
    if bad_row is not None:
        return ValidationResult(
            "invalid",
            f"row_width_mismatch at index {bad_row}: expected {width}",
            len(data),
        )

    extras = field_set - COMPANY_TICKERS_EXCHANGE_REQUIRED_FIELDS
    if extras:
        return ValidationResult(
            "schema_drift", f"new_fields: {sorted(extras)}", len(data)
        )
    return ValidationResult("ok", None, len(data))
