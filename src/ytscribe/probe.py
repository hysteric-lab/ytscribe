"""Probe videos for caption availability — the scan core. No downloads."""
from __future__ import annotations

import json
import subprocess

from ytscribe.manifest import VideoEntry


def _default_fetcher(video_id: str) -> dict | None:
    try:
        proc = subprocess.run(
            ["yt-dlp", "-J", "--skip-download",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


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


def probe_videos(video_ids, metadata_fetcher=_default_fetcher) -> list[VideoEntry]:
    entries = []
    for vid in video_ids:
        meta = metadata_fetcher(vid)
        entries.append(_skipped_entry(vid) if meta is None
                       else _entry_from_metadata(vid, meta))
    return entries
