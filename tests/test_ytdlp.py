import logging
import subprocess

import pytest

from ytscribe import _ytdlp


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_ytdlp_injects_cookies_and_proxy(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed()

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    _ytdlp.run_ytdlp(["-J", "https://youtu.be/x"], timeout_s=30,
                     cookies_file="/data/cookies.txt", proxy="http://p:1",
                     log_event="probe.metadata")
    assert captured["cmd"] == [
        "yt-dlp", "--cookies", "/data/cookies.txt", "--proxy", "http://p:1",
        "-J", "https://youtu.be/x"]


def test_run_ytdlp_omits_flags_when_unset(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed()

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None, proxy=None,
                     log_event="probe.metadata")
    assert captured["cmd"] == ["yt-dlp", "-J", "x"]


def test_run_ytdlp_redacts_cookies_and_proxy_in_log(monkeypatch, caplog):
    monkeypatch.setattr(_ytdlp.subprocess, "run",
                        lambda cmd, **kw: _completed())
    with caplog.at_level(logging.INFO, logger="ytscribe.ytdlp"):
        _ytdlp.run_ytdlp(["-J", "https://youtu.be/x"], timeout_s=30,
                         cookies_file="/secret/cookies.txt",
                         proxy="http://user:pw@host:1", log_event="probe.metadata")
    record = caplog.records[-1]
    assert "/secret/cookies.txt" not in record.ytdlp_args
    assert "http://user:pw@host:1" not in record.ytdlp_args
    assert "<redacted>" in record.ytdlp_args
    assert "<set>" in record.ytdlp_args


def test_run_ytdlp_returns_nonzero_and_logs_warn_with_tails(monkeypatch, caplog):
    monkeypatch.setattr(
        _ytdlp.subprocess, "run",
        lambda cmd, **kw: _completed(returncode=1,
                                     stderr="ERROR: HTTP Error 429: Too Many Requests"))
    with caplog.at_level(logging.INFO, logger="ytscribe.ytdlp"):
        proc = _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None,
                                proxy=None, log_event="probe.metadata")
    assert proc.returncode == 1  # returned, never raised
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "429" in warnings[0].stderr_tail


def test_run_ytdlp_logs_timeout_and_reraises(monkeypatch, caplog):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    with caplog.at_level(logging.WARNING, logger="ytscribe.ytdlp"):
        with pytest.raises(subprocess.TimeoutExpired):
            _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None,
                             proxy=None, log_event="probe.metadata")
    record = caplog.records[-1]
    assert record.timed_out is True
    assert record.exit_code is None
