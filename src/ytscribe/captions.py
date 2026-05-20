"""Fetch and clean existing YouTube caption tracks."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from ytscribe.models import Segment, Transcript

_TS = re.compile(
    r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d)\.(\d\d\d)"
)


def _to_seconds(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def clean_vtt(vtt_text: str) -> list[Segment]:
    segments: list[Segment] = []
    lines = vtt_text.splitlines()
    i = 0
    while i < len(lines):
        m = _TS.search(lines[i])
        if not m:
            i += 1
            continue
        start = _to_seconds(*m.groups()[:4])
        end = _to_seconds(*m.groups()[4:])
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip() and not _TS.search(lines[i]):
            text_lines.append(re.sub(r"<[^>]+>", "", lines[i]).strip())
            i += 1
        text = " ".join(t for t in text_lines if t)
        if text:
            segments.append(Segment(start, end, text))
    return segments


def _default_downloader(video_id: str, lang: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cap"
        try:
            subprocess.run(
                ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
                 "--sub-langs", lang, "--sub-format", "vtt",
                 "-o", str(out), f"https://www.youtube.com/watch?v={video_id}"],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            return ""
        for f in sorted(Path(tmp).glob("cap*.vtt")):
            return f.read_text(encoding="utf-8")
    return ""


def fetch_caption(video_id: str, lang: str, downloader=_default_downloader) -> Transcript:
    vtt = downloader(video_id, lang)
    segments = clean_vtt(vtt) if vtt else []
    if not segments:
        raise RuntimeError(f"no caption content for {video_id} ({lang})")
    return Transcript(video_id=video_id, language=lang, segments=segments)
