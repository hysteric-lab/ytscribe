"""Render a Transcript to txt / srt / json and write it to disk."""
from __future__ import annotations

import json
from pathlib import Path

from ytscribe.models import Transcript

FORMATS = ("txt", "srt", "json")


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render(transcript: Transcript, fmt: str) -> str:
    if fmt == "txt":
        return transcript.full_text
    if fmt == "json":
        return json.dumps(
            {
                "video_id": transcript.video_id,
                "language": transcript.language,
                "segments": [
                    {"start_s": s.start_s, "end_s": s.end_s, "text": s.text}
                    for s in transcript.segments
                ],
            },
            ensure_ascii=False, indent=2,
        )
    if fmt == "srt":
        blocks = []
        for i, s in enumerate(transcript.segments, start=1):
            blocks.append(
                f"{i}\n{_srt_time(s.start_s)} --> {_srt_time(s.end_s)}\n{s.text}\n"
            )
        return "\n".join(blocks)
    raise ValueError(f"unknown format: {fmt!r} (expected one of {FORMATS})")


def write_output(transcript: Transcript, out_dir: Path, fmt: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{transcript.video_id}.{fmt}"
    path.write_text(render(transcript, fmt), encoding="utf-8")
    return path
