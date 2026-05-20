"""The manifest: scan writes the plan, fetch writes back results."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ytscribe import __version__

SCHEMA_VERSION = __version__


@dataclass
class VideoEntry:
    id: str
    title: str
    duration_s: int
    captions: dict            # {"manual": [...], "auto": [...]}
    detected_language: str
    planned_action: str       # "caption" | "asr" | "skip"
    planned_reason: str
    status: str = "pending"   # "pending" | "done" | "failed"
    output_path: str | None = None
    error: str | None = None


@dataclass
class Manifest:
    source: dict
    scope: dict
    videos: list[VideoEntry] = field(default_factory=list)
    engine_version: str = SCHEMA_VERSION
    created_at: str = ""

    def summary(self) -> dict:
        return {
            "total": len(self.videos),
            "have_caption": sum(v.planned_action == "caption" for v in self.videos),
            "need_asr": sum(v.planned_action == "asr" for v in self.videos),
            "skip": sum(v.planned_action == "skip" for v in self.videos),
        }

    def pending(self) -> list[VideoEntry]:
        return [v for v in self.videos if v.status == "pending"]

    def save(self, path: Path) -> None:
        path = Path(path)
        doc = {
            "engine_version": self.engine_version,
            "created_at": self.created_at,
            "source": self.source,
            "scope": self.scope,
            "videos": [asdict(v) for v in self.videos],
            "summary": self.summary(),
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            source=doc["source"],
            scope=doc["scope"],
            videos=[VideoEntry(**v) for v in doc["videos"]],
            engine_version=doc.get("engine_version", ""),
            created_at=doc.get("created_at", ""),
        )
