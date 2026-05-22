"""Download audio for ASR. Cleans stray partials on timeout, then raises."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config


def _make_default_runner(config: Config):
    """Build the default audio runner bound to a Config (cookies/proxy)."""
    def runner(video_id: str, out_dir: Path, timeout_s: int) -> Path:
        out_tmpl = str(Path(out_dir) / f"{video_id}.%(ext)s")
        proc = run_ytdlp(
            ["-x", "--audio-format", "mp3", "--audio-quality", "5",
             "-o", out_tmpl, f"https://www.youtube.com/watch?v={video_id}"],
            timeout_s=timeout_s,
            cookies_file=config.cookies_file,
            proxy=config.proxy,
            log_event="audio.download",
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, proc.args, output=proc.stdout, stderr=proc.stderr)
        return Path(out_dir) / f"{video_id}.mp3"
    return runner


def _clean_strays(video_id: str, out_dir: Path) -> None:
    for stray in Path(out_dir).glob(f"{video_id}.*"):
        try:
            stray.unlink()
        except OSError:
            pass


def download_audio(video_id: str, out_dir: Path, timeout_s: int,
                   runner=None, config: Config | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if runner is None:
        runner = _make_default_runner(config if config is not None else Config.from_env())
    try:
        return runner(video_id, out_dir, timeout_s)
    except subprocess.TimeoutExpired as exc:
        _clean_strays(video_id, out_dir)
        raise RuntimeError(
            f"audio download timeout for {video_id} after {timeout_s}s"
        ) from exc
    except subprocess.CalledProcessError as exc:
        _clean_strays(video_id, out_dir)
        raise RuntimeError(f"audio download failed for {video_id} (yt-dlp error)") from exc
