"""Tests for the notification fan-out.

Network and subprocess are both mocked via dependency injection so these
remain pure unit tests.
"""

import json
import subprocess

import pytest

from timemachine.manifest import FileEntry
from timemachine.notify import (
    NOTIFY_STATUSES,
    emit_notifications,
    gh_issue_upsert,
    needs_notification,
    telegram_send,
)


def _entry(
    *, name: str = "nasdaqtraded.txt", status: str = "invalid", reason: str | None = "bad"
) -> FileEntry:
    return FileEntry(
        name=name,
        status=status,
        stored_path=None,
        sha256=None,
        row_count=0,
        file_creation_time=None,
        reason=reason,
    )


# --- needs_notification ----------------------------------------------------


@pytest.mark.parametrize(
    "status, expected",
    [
        ("ok", False),
        ("invalid", True),
        ("missing", True),
        ("schema_drift", True),
        ("discovered", True),
        ("weird_status", False),
    ],
)
def test_needs_notification_classifies_statuses(status, expected):
    assert needs_notification(_entry(status=status)) is expected


def test_NOTIFY_STATUSES_is_a_frozenset_of_four_values():
    assert isinstance(NOTIFY_STATUSES, frozenset)
    assert {"invalid", "missing", "schema_drift", "discovered"} == NOTIFY_STATUSES


# --- telegram_send ---------------------------------------------------------


def test_telegram_send_silent_when_env_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert telegram_send("hi") is False


def test_telegram_send_dispatches_when_env_present(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "CHAT456")

    captured: dict = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_opener(req, _timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.headers)
        return FakeResp()

    assert telegram_send("hello world", opener=fake_opener) is True
    assert captured["url"] == "https://api.telegram.org/botTOKEN123/sendMessage"
    assert captured["body"] == {"chat_id": "CHAT456", "text": "hello world"}
    assert captured["headers"]["Content-type"] == "application/json"


# --- gh_issue_upsert -------------------------------------------------------


def test_gh_issue_upsert_creates_when_no_existing(monkeypatch):
    calls: list[list[str]] = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    assert gh_issue_upsert("X", "body", ["a"], runner=fake_runner) is True
    assert any(c[:3] == ["gh", "issue", "list"] for c in calls)
    assert any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert not any(c[:3] == ["gh", "issue", "comment"] for c in calls)


def test_gh_issue_upsert_comments_when_open_issue_with_same_title_exists():
    calls: list[list[str]] = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps([{"number": 42, "title": "X"}]), stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    assert gh_issue_upsert("X", "body", ["a"], runner=fake_runner) is True
    comment_cmd = next((c for c in calls if c[:3] == ["gh", "issue", "comment"]), None)
    assert comment_cmd is not None
    assert "42" in comment_cmd
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)


def test_gh_issue_upsert_returns_false_when_gh_missing():
    def fake_runner(cmd, **kwargs):
        raise FileNotFoundError("gh: command not found")

    assert gh_issue_upsert("X", "body", [], runner=fake_runner) is False


# --- emit_notifications ----------------------------------------------------


def test_emit_notifications_silent_when_no_anomalies():
    tg_calls: list[str] = []
    iss_calls: list[tuple[str, str, list[str]]] = []
    emit_notifications(
        anomalies=[],
        telegram_fn=lambda m: tg_calls.append(m) or True,
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or True,
    )
    assert tg_calls == []
    assert iss_calls == []


def test_emit_notifications_sends_one_telegram_and_one_issue_per_unique_name():
    anomalies = [
        _entry(name="nasdaqtraded.txt", status="invalid", reason="header_mismatch"),
        _entry(name="nasdaqtraded.txt", status="invalid", reason="header_mismatch"),  # dup
        _entry(name="nasdaqlisted.txt", status="missing", reason="HTTP 503"),
        _entry(name="discovery:regshopilotlist/", status="discovered", reason="new dir"),
    ]
    tg_calls: list[str] = []
    iss_calls: list[tuple[str, str, list[str]]] = []
    emit_notifications(
        anomalies=anomalies,
        telegram_fn=lambda m: tg_calls.append(m) or True,
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or True,
    )

    assert len(tg_calls) == 1
    assert "us-markets-timemachine" in tg_calls[0]
    assert "invalid" in tg_calls[0]
    assert "missing" in tg_calls[0]
    assert "discovered" in tg_calls[0]

    # 3 unique titles (the duplicate nasdaqtraded entry collapses).
    titles = [c[0] for c in iss_calls]
    assert len(titles) == 3
    assert "[invalid] nasdaqtraded.txt" in titles
    assert "[missing] nasdaqlisted.txt" in titles
    assert "[discovered] discovery:regshopilotlist/" in titles


def test_emit_notifications_issue_labels_reflect_kind_and_status():
    iss_calls: list[tuple[str, str, list[str]]] = []
    emit_notifications(
        anomalies=[
            _entry(name="nasdaqtraded.txt", status="invalid"),
            _entry(name="regsho/nasdaqth20240514.txt", status="missing"),
            _entry(name="discovery:foo.txt", status="discovered"),
        ],
        telegram_fn=lambda _m: True,
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or True,
    )
    by_title = {t: labels for t, _b, labels in iss_calls}
    assert "kind:capture" in by_title["[invalid] nasdaqtraded.txt"]
    assert "kind:mirror" in by_title["[missing] regsho/nasdaqth20240514.txt"]
    assert "kind:discovery" in by_title["[discovered] discovery:foo.txt"]
    for labels in by_title.values():
        assert "worker-anomaly" in labels
