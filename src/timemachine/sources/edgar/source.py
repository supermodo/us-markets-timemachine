"""EdgarSource — implements the Source protocol for SEC EDGAR ticker mappings.

Behavior:
    * `should_run(today)` — true on US weekdays. SEC publishes weekday-only;
      Saturday/Sunday fetches return the same Friday payload, so skipping them
      keeps the manifest honest about cadence.
    * `snapshot(...)` — fetches `company_tickers.json` and
      `company_tickers_exchange.json` with a User-Agent that includes the
      operator's contact email (SEC requirement). Rejects HTML maintenance
      pages, validates JSON shape, writes gzipped copies under
      `data/edgar/<file>/<YYYY>/<YYYY-MM-DD>.gz`.

SEC's published rate limit is 10 req/s; this source makes 2 requests, well
under it. No throttling is needed.

Configuration:
    TIMEMACHINE_CONTACT_EMAIL — operator's email, embedded in User-Agent.
                                Required. Without it, SEC silently 403s.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from timemachine.http import FetchError
from timemachine.http import fetch as default_fetch
from timemachine.io import sha256_hex, write_gz
from timemachine.manifest import FileEntry
from timemachine.paths import captured_path, rejected_path
from timemachine.sources.edgar.config import CAPTURED_FILES, EdgarFile

CONTACT_ENV_VAR = "TIMEMACHINE_CONTACT_EMAIL"
DEFAULT_CONTACT_EMAIL = "servizio@modotti.me"

Fetcher = Callable[..., bytes]


class EdgarConfigError(RuntimeError):
    """Raised when EDGAR cannot start because required configuration is missing."""


@dataclass(frozen=True)
class EdgarSource:
    name: str = "edgar"
    display_name: str = "SEC EDGAR ticker mappings"
    specs: tuple[EdgarFile, ...] = field(default_factory=lambda: CAPTURED_FILES)

    def should_run(self, today: date) -> bool:
        # Weekday filter only. Federal-holiday awareness can come later;
        # capturing on a holiday just snapshots Friday's payload again, which
        # is faithful to what SEC actually serves and gets recorded as such.
        return today.weekday() < 5  # Mon-Fri

    def snapshot(
        self,
        *,
        data_root: Path,
        today: date,
        dry_run: bool = False,
        fetcher: Fetcher | None = None,
    ) -> Iterable[FileEntry]:
        contact = _resolve_contact_email()
        ua = _build_user_agent(contact)
        fetch_fn = fetcher if fetcher is not None else default_fetch
        return [
            _capture_one(
                spec,
                data_root=data_root,
                today=today,
                fetcher=fetch_fn,
                user_agent=ua,
                dry_run=dry_run,
            )
            for spec in self.specs
        ]


# ---------------------------------------------------------------------------


def _capture_one(
    spec: EdgarFile,
    *,
    data_root: Path,
    today: date,
    fetcher: Fetcher,
    user_agent: str,
    dry_run: bool,
) -> FileEntry:
    try:
        content = fetcher(spec.url, user_agent=user_agent)
    except FetchError as e:
        return FileEntry(
            name=spec.name,
            status="missing",
            stored_path=None,
            sha256=None,
            row_count=0,
            file_creation_time=None,
            reason=str(e),
            source="edgar",
        )

    result = spec.validator(content, spec)
    sha = sha256_hex(content)

    if result.status == "invalid":
        target = rejected_path(data_root, "edgar", spec.name, today)
        if not dry_run:
            write_gz(target, content)
        return FileEntry(
            name=spec.name,
            status="invalid",
            stored_path=_repo_relative(target, data_root),
            sha256=sha,
            row_count=result.row_count,
            file_creation_time=None,
            reason=result.reason,
            source="edgar",
        )

    target = captured_path(data_root, "edgar", spec, today)
    if target.exists():
        return FileEntry(
            name=spec.name,
            status=result.status,
            stored_path=_repo_relative(target, data_root),
            sha256=sha,
            row_count=result.row_count,
            file_creation_time=None,
            reason="already_existed_not_overwritten",
            source="edgar",
        )

    if not dry_run:
        write_gz(target, content)

    return FileEntry(
        name=spec.name,
        status=result.status,
        stored_path=_repo_relative(target, data_root),
        sha256=sha,
        row_count=result.row_count,
        file_creation_time=None,
        reason=result.reason,
        source="edgar",
    )


def _resolve_contact_email() -> str:
    """Resolve the operator's contact email from env, falling back to the project default.

    The default is intended for local dev only; CI must set the env var so each
    operator's archive is identifiable to SEC if they ever ask.
    """
    return os.environ.get(CONTACT_ENV_VAR, "").strip() or DEFAULT_CONTACT_EMAIL


def _build_user_agent(contact_email: str) -> str:
    if "@" not in contact_email or " " in contact_email:
        raise EdgarConfigError(
            f"{CONTACT_ENV_VAR} must be a single email address (got {contact_email!r}); "
            "SEC requires a contactable email in the User-Agent or it will block requests."
        )
    return f"us-markets-timemachine/0.1 ({contact_email})"


def _repo_relative(target: Path, data_root: Path) -> str:
    repo_root = data_root.parent
    try:
        return str(target.relative_to(repo_root))
    except ValueError:
        return str(target)
