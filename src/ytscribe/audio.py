"""Download audio for ASR. Cleans stray partials on timeout, then raises."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _default_runner(video_id: str, out_dir: Path, timeout_s: int) -> Path:
    out_tmpl = str(Path(out_dir) / f"{video_id}.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
         "-o", out_tmpl, f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=timeout_s, check=True,
    )
    return Path(out_dir) / f"{video_id}.mp3"


def _clean_strays(video_id: str, out_dir: Path) -> None:
    for stray in Path(out_dir).glob(f"{video_id}.*"):
        try:
            stray.unlink()
        except OSError:
            pass


def download_audio(video_id: str, out_dir: Path, timeout_s: int,
                   runner=_default_runner) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return runner(video_id, out_dir, timeout_s)
    except subprocess.TimeoutExpired:
        _clean_strays(video_id, out_dir)
        raise RuntimeError(f"audio download timeout for {video_id} after {timeout_s}s")
