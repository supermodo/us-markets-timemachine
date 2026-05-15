"""Tests for the notification fan-out.

Network and subprocess are both mocked via dependency injection so these
remain pure unit tests.
"""

import json
import subprocess
from urllib.request import Request

import pytest

from timemachine import notify
from timemachine.manifest import FileEntry
from timemachine.notify import (
    NOTIFY_STATUSES,
    _default_opener,
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


def test_default_opener_forwards_timeout_as_kwarg(monkeypatch):
    # Regression: a previous implementation called urlopen(req, 10) positionally,
    # which bound 10 to urlopen's `data` parameter instead of `timeout`,
    # crashing downstream in http.client when it tried to send an int as the
    # request body. The default opener must forward `timeout` as a kwarg.
    captured: dict = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeResp()

    monkeypatch.setattr(notify, "urlopen", fake_urlopen)
    with _default_opener(Request("https://example.test/"), 10.0):
        pass

    # The Request goes positional, timeout MUST be kwarg.
    assert len(captured["args"]) == 1
    assert isinstance(captured["args"][0], Request)
    assert captured["kwargs"] == {"timeout": 10.0}


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


def test_gh_issue_upsert_creates_when_no_existing_returns_new_url():
    calls: list[list[str]] = []
    new_url = "https://github.com/owner/repo/issues/42"

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:3] == ["gh", "issue", "create"]:
            # gh prints the new issue URL on stdout.
            return subprocess.CompletedProcess(cmd, 0, stdout=new_url + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    assert gh_issue_upsert("X", "body", ["a"], runner=fake_runner) == new_url
    assert any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert not any(c[:3] == ["gh", "issue", "comment"] for c in calls)


def test_gh_issue_upsert_comments_when_open_issue_exists_returns_existing_url():
    calls: list[list[str]] = []
    existing_url = "https://github.com/owner/repo/issues/42"

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    [{"number": 42, "title": "X", "url": existing_url}]
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    assert gh_issue_upsert("X", "body", ["a"], runner=fake_runner) == existing_url
    comment_cmd = next((c for c in calls if c[:3] == ["gh", "issue", "comment"]), None)
    assert comment_cmd is not None
    assert "42" in comment_cmd
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)


def test_gh_issue_upsert_returns_none_when_gh_missing():
    def fake_runner(cmd, **kwargs):
        raise FileNotFoundError("gh: command not found")

    assert gh_issue_upsert("X", "body", [], runner=fake_runner) is None


# --- emit_notifications ----------------------------------------------------


def test_emit_notifications_silent_when_no_anomalies():
    tg_calls: list[str] = []
    iss_calls: list[tuple[str, str, list[str]]] = []
    emit_notifications(
        anomalies=[],
        telegram_fn=lambda m: tg_calls.append(m) or True,
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or None,
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
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or None,
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


def test_emit_notifications_telegram_message_includes_issue_urls():
    anomalies = [
        _entry(name="nasdaqtraded.txt", status="invalid", reason="header_mismatch"),
        _entry(name="discovery:foo/", status="discovered", reason="new dir"),
    ]
    urls = {
        "[invalid] nasdaqtraded.txt": "https://github.com/owner/repo/issues/1",
        "[discovered] discovery:foo/": "https://github.com/owner/repo/issues/2",
    }
    tg_msgs: list[str] = []
    call_order: list[str] = []

    def telegram_fn(msg):
        call_order.append("tg")
        tg_msgs.append(msg)
        return True

    def issue_fn(title, _body, _labels):
        call_order.append("iss")
        return urls[title]

    emit_notifications(anomalies=anomalies, telegram_fn=telegram_fn, issue_fn=issue_fn)

    # Issues must be processed BEFORE telegram so URLs can be inlined.
    assert call_order == ["iss", "iss", "tg"]
    msg = tg_msgs[0]
    assert "https://github.com/owner/repo/issues/1" in msg
    assert "https://github.com/owner/repo/issues/2" in msg


def test_emit_notifications_telegram_still_fires_when_issue_creation_fails():
    # Issue creation can fail (gh missing, network, etc.) — the worker must
    # still notify the on-call channel, just without a URL.
    anomalies = [_entry(name="x.txt", status="invalid", reason="bad")]
    tg_msgs: list[str] = []
    emit_notifications(
        anomalies=anomalies,
        telegram_fn=lambda m: tg_msgs.append(m) or True,
        issue_fn=lambda *_: None,
    )
    assert len(tg_msgs) == 1
    assert "x.txt" in tg_msgs[0]
    assert "https://github.com/" not in tg_msgs[0]


def test_emit_notifications_issue_labels_reflect_kind_and_status():
    iss_calls: list[tuple[str, str, list[str]]] = []
    emit_notifications(
        anomalies=[
            _entry(name="nasdaqtraded.txt", status="invalid"),
            _entry(name="regsho/nasdaqth20240514.txt", status="missing"),
            _entry(name="discovery:foo.txt", status="discovered"),
        ],
        telegram_fn=lambda _m: True,
        issue_fn=lambda t, b, lbl: iss_calls.append((t, b, lbl)) or None,
    )
    by_title = {t: labels for t, _b, labels in iss_calls}
    assert "kind:capture" in by_title["[invalid] nasdaqtraded.txt"]
    assert "kind:mirror" in by_title["[missing] regsho/nasdaqth20240514.txt"]
    assert "kind:discovery" in by_title["[discovered] discovery:foo.txt"]
    for labels in by_title.values():
        assert "worker-anomaly" in labels
