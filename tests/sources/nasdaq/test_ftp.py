"""Retry behaviour of the FTP listing, driven through the public listers.

Network is replaced by a scripted stand-in for ftplib.FTP.
"""

from ftplib import error_perm, error_temp

import pytest

from timemachine.sources.nasdaq import ftp
from timemachine.sources.nasdaq.discovery import SymDirEntry, ftp_list_symdir
from timemachine.sources.nasdaq.mirror import ftp_list_archive

LINE = "11-02-26  08:00PM   100 shorthalts20261102.txt"


class ScriptedFTP:
    """Each connection plays the next outcome: lines to list, or an error to raise."""

    def __init__(self, outcomes: list):
        self.outcomes = outcomes
        self.connections = 0

    def __call__(self, _host: str, timeout: float) -> "ScriptedFTP":
        self.connections += 1
        self.current = self.outcomes.pop(0)
        return self

    def __enter__(self) -> "ScriptedFTP":
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def login(self) -> None:
        pass

    def cwd(self, _directory: str) -> None:
        pass

    def retrlines(self, _cmd: str, callback) -> None:
        lines, error = self.current
        for line in lines:
            callback(line)
        if error is not None:
            raise error


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(ftp.time, "sleep", recorded.append)
    return recorded


def _script(monkeypatch: pytest.MonkeyPatch, *outcomes) -> ScriptedFTP:
    scripted = ScriptedFTP(list(outcomes))
    monkeypatch.setattr(ftp, "FTP", scripted)
    return scripted


def test_archive_listing_recovers_from_a_single_timeout(monkeypatch, sleeps):
    scripted = _script(monkeypatch, ([], TimeoutError("timed out")), ([LINE], None))

    assert ftp_list_archive("shorthalts") == ["shorthalts20261102.txt"]
    assert scripted.connections == 2
    assert len(sleeps) == 1


def test_symdir_listing_recovers_from_a_single_timeout(monkeypatch, sleeps):
    line = "11-02-26  08:00PM   <DIR>   shorthalts"
    _script(monkeypatch, ([], TimeoutError("timed out")), ([line], None))

    assert ftp_list_symdir() == [SymDirEntry(name="shorthalts", is_directory=True)]


def test_lines_from_an_interrupted_attempt_are_not_kept(monkeypatch, sleeps):
    other = "11-03-26  08:00PM   100 shorthalts20261103.txt"
    _script(monkeypatch, ([LINE], TimeoutError("timed out")), ([LINE, other], None))

    assert ftp_list_archive("shorthalts") == [
        "shorthalts20261102.txt",
        "shorthalts20261103.txt",
    ]


def test_temporary_ftp_reply_is_retried(monkeypatch, sleeps):
    _script(monkeypatch, ([], error_temp("421 service not available")), ([LINE], None))

    assert ftp_list_archive("shorthalts") == ["shorthalts20261102.txt"]


def test_exhausted_attempts_raise_the_last_error(monkeypatch, sleeps):
    scripted = _script(
        monkeypatch,
        ([], TimeoutError("first")),
        ([], TimeoutError("second")),
        ([], TimeoutError("timed out")),
    )

    with pytest.raises(TimeoutError, match="timed out"):
        ftp_list_archive("shorthalts")
    assert scripted.connections == 3
    assert len(sleeps) == 2


def test_permanent_ftp_reply_is_not_retried(monkeypatch, sleeps):
    scripted = _script(monkeypatch, ([], error_perm("550 no such directory")), ([LINE], None))

    with pytest.raises(error_perm):
        ftp_list_archive("shorthalts")
    assert scripted.connections == 1
    assert sleeps == []
