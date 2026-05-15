"""Notification fan-out — interview answers + spec resilience contract.

Two channels, both optional, both silent when their config is absent:

    1. Telegram bot — urllib POST to api.telegram.org. Silent if either of
       TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars is missing. One summary
       message per run.

    2. GitHub issue — shells out to `gh` CLI (pre-installed on Actions
       runners). Dedup by title: if an open issue with the same title already
       exists, comment on it instead of creating a duplicate. One issue per
       unique anomaly key.

Per the interview answer "Telegram only on failure or anomaly", notifications
fire ONLY when there is at least one FileEntry with a status in
NOTIFY_STATUSES. A clean run emits nothing on either channel.
"""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from timemachine.manifest import FileEntry

# Statuses that warrant an alert.
# `ok` is silent. `schema_drift` and `discovered` are flags — quiet but worth
# surfacing to the human. `invalid` / `missing` are failures.
NOTIFY_STATUSES = frozenset({"invalid", "missing", "schema_drift", "discovered"})


def needs_notification(entry: FileEntry) -> bool:
    return entry.status in NOTIFY_STATUSES


# --- Telegram ---------------------------------------------------------------

# Injectable for tests; defaults to urllib.request.urlopen.
HttpPoster = Callable[[Request, float], object]


def telegram_send(message: str, *, opener: HttpPoster | None = None) -> bool:
    """Send `message` to the configured Telegram chat. Returns True if dispatched."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False

    payload = json.dumps({"chat_id": chat, "text": message}).encode()
    req = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    poster = opener or urlopen
    try:
        with poster(req, 10) as resp:
            status = getattr(resp, "status", None)
            return status is None or status == 200
    except URLError as e:
        print(f"telegram send failed: {e}", file=sys.stderr)
        return False


# --- GitHub issue (via `gh` CLI) -------------------------------------------

# Injectable for tests; defaults to subprocess.run.
Runner = Callable[..., subprocess.CompletedProcess]


def gh_issue_upsert(
    title: str,
    body: str,
    labels: list[str],
    *,
    runner: Runner | None = None,
) -> bool:
    """Create or update an open GitHub issue keyed by title.

    Returns True on success, False if `gh` is unavailable or fails. Designed
    to fail-soft: notification failures must not crash the worker, since the
    worker has already succeeded at the data work by the time we get here.
    """
    run = runner or subprocess.run
    try:
        existing_proc = run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--search",
                f'in:title "{title}"',
                "--json",
                "number,title",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"gh issue list failed: {e}", file=sys.stderr)
        return False

    try:
        existing = json.loads(existing_proc.stdout or "[]")
    except json.JSONDecodeError as e:
        print(f"gh issue list returned malformed JSON: {e}", file=sys.stderr)
        return False

    match = next((iss for iss in existing if iss.get("title") == title), None)

    try:
        if match is not None:
            run(
                ["gh", "issue", "comment", str(match["number"]), "--body", body],
                check=True,
                timeout=30,
            )
        else:
            cmd = ["gh", "issue", "create", "--title", title, "--body", body]
            for label in labels:
                cmd.extend(["--label", label])
            run(cmd, check=True, timeout=30)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"gh issue upsert failed: {e}", file=sys.stderr)
        return False


# --- High-level fan-out ----------------------------------------------------


def emit_notifications(
    anomalies: list[FileEntry],
    *,
    telegram_fn: Callable[[str], bool] | None = None,
    issue_fn: Callable[[str, str, list[str]], bool] | None = None,
) -> None:
    if not anomalies:
        return

    tg = telegram_fn or telegram_send
    iss = issue_fn or gh_issue_upsert

    tg(_format_telegram_summary(anomalies))

    seen_titles: set[str] = set()
    for entry in anomalies:
        title = _issue_title(entry)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        same_title = [e for e in anomalies if _issue_title(e) == title]
        iss(title, _issue_body(same_title), _labels_for(entry))


def _format_telegram_summary(anomalies: list[FileEntry]) -> str:
    counts: dict[str, int] = {}
    for e in anomalies:
        counts[e.status] = counts.get(e.status, 0) + 1
    parts = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    lines = [f"us-markets-timemachine: {parts}"]
    for e in anomalies[:10]:
        lines.append(f"  - [{e.status}] {e.name}{(': ' + e.reason) if e.reason else ''}")
    if len(anomalies) > 10:
        lines.append(f"  ... +{len(anomalies) - 10} more")
    return "\n".join(lines)


def _issue_title(entry: FileEntry) -> str:
    return f"[{entry.status}] {entry.name}"


def _issue_body(entries_for_title: list[FileEntry]) -> str:
    lines = []
    for e in entries_for_title:
        lines.append(f"- **status:** `{e.status}`")
        if e.reason:
            lines.append(f"- **reason:** {e.reason}")
        if e.stored_path:
            lines.append(f"- **stored_path:** `{e.stored_path}`")
        if e.sha256:
            lines.append(f"- **sha256:** `{e.sha256}`")
        if e.row_count:
            lines.append(f"- **row_count:** {e.row_count}")
        if e.file_creation_time:
            lines.append(f"- **upstream_creation_time:** `{e.file_creation_time}`")
        lines.append("")
    lines.append("---")
    lines.append("_Auto-opened by `us-markets-timemachine` daily worker. Closing this issue without resolving will reopen the next time the anomaly recurs._")
    return "\n".join(lines)


def _labels_for(entry: FileEntry) -> list[str]:
    base = ["worker-anomaly", f"status:{entry.status}"]
    if entry.name.startswith("discovery:"):
        base.append("kind:discovery")
    elif "/" in entry.name:
        base.append("kind:mirror")
    else:
        base.append("kind:capture")
    return base
