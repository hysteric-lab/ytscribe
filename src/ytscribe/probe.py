"""Probe videos for caption availability — the scan core. No downloads."""
from __future__ import annotations

import json
import subprocess

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config
from ytscribe.manifest import VideoEntry


def _make_default_fetcher(config: Config):
    """Build a yt-dlp metadata fetcher bound to a Config (timeout, cookies, proxy)."""
    def fetcher(video_id: str) -> dict | None:
        try:
            proc = run_ytdlp(
                ["-J", "--skip-download",
                 f"https://www.youtube.com/watch?v={video_id}"],
                timeout_s=config.probe_timeout_s,
                cookies_file=config.cookies_file,
                proxy=config.proxy,
                log_event="probe.metadata",
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
    return fetcher


def _entry_from_metadata(video_id: str, meta: dict) -> VideoEntry:
    manual = sorted((meta.get("subtitles") or {}).keys())
    auto = sorted((meta.get("automatic_captions") or {}).keys())
    has_caption = bool(manual or auto)
    return VideoEntry(
        id=video_id,
        title=meta.get("title", video_id),
        duration_s=int(meta.get("duration") or 0),
        captions={"manual": manual, "auto": auto},
        detected_language=meta.get("language") or "",
        planned_action="caption" if has_caption else "asr",
        planned_reason="caption available" if has_caption else "no caption -> asr",
    )


def _skipped_entry(video_id: str) -> VideoEntry:
    return VideoEntry(
        id=video_id, title=video_id, duration_s=0,
        captions={"manual": [], "auto": []}, detected_language="",
        planned_action="skip", planned_reason="unprobeable",
    )


def probe_videos(video_ids, metadata_fetcher=None,
                 config: Config | None = None) -> list[VideoEntry]:
    if metadata_fetcher is None:
        metadata_fetcher = _make_default_fetcher(
            config if config is not None else Config.from_env())
    entries = []
    for vid in video_ids:
        meta = metadata_fetcher(vid)
        entries.append(_skipped_entry(vid) if meta is None
                       else _entry_from_metadata(vid, meta))
    return entries
