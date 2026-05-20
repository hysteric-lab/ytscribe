"""Shared data types for transcripts."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    start_s: float
    end_s: float
    text: str


@dataclass
class Transcript:
    video_id: str
    language: str
    segments: list[Segment] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @classmethod
    def from_plain_text(cls, video_id: str, language: str, text: str) -> "Transcript":
        return cls(video_id, language, [Segment(0.0, 0.0, text.strip())])
