# tests/test_audio.py
import subprocess

import pytest

from ytscribe.audio import download_audio


def test_download_audio_returns_path_on_success(tmp_path):
    target = tmp_path / "vid12345678.mp3"

    def fake_run(video_id, out_dir, timeout_s):
        target.write_bytes(b"fake mp3")
        return target

    path = download_audio("vid12345678", tmp_path, timeout_s=300, runner=fake_run)
    assert path == target
    assert path.exists()


def test_download_audio_timeout_cleans_and_raises(tmp_path):
    stray = tmp_path / "vid12345678.part"
    stray.write_bytes(b"partial")

    def fake_run(video_id, out_dir, timeout_s):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=timeout_s)

    with pytest.raises(RuntimeError, match="audio download timeout"):
        download_audio("vid12345678", tmp_path, timeout_s=300, runner=fake_run)
    assert not stray.exists()  # stray partial cleaned


def test_download_audio_yt_dlp_error_cleans_and_raises(tmp_path):
    stray = tmp_path / "vid12345678.part"
    stray.write_bytes(b"partial")

    def fake_run(video_id, out_dir, timeout_s):
        raise subprocess.CalledProcessError(returncode=1, cmd="yt-dlp")

    with pytest.raises(RuntimeError, match="audio download failed"):
        download_audio("vid12345678", tmp_path, timeout_s=300, runner=fake_run)
    assert not stray.exists()  # stray partial cleaned on yt-dlp error too


def test_default_runner_passes_cookies_and_proxy_to_wrapper(monkeypatch, tmp_path):
    import ytscribe.audio as audio
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        seen["timeout_s"] = timeout_s
        seen["log_event"] = log_event
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(audio, "run_ytdlp", fake_run_ytdlp)
    runner = audio._make_default_runner(Config(cookies_file="/c.txt", proxy="http://p:1"))
    path = runner("vid12345678", tmp_path, timeout_s=300)
    assert path == tmp_path / "vid12345678.mp3"
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1",
                    "timeout_s": 300, "log_event": "audio.download"}


def test_default_runner_raises_called_process_error_on_nonzero(monkeypatch, tmp_path):
    import ytscribe.audio as audio
    from ytscribe.config import Config

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=1,
                                           stdout="", stderr="boom")

    monkeypatch.setattr(audio, "run_ytdlp", fake_run_ytdlp)
    runner = audio._make_default_runner(Config())
    with pytest.raises(subprocess.CalledProcessError):
        runner("vid12345678", tmp_path, timeout_s=300)
