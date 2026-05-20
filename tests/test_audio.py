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
