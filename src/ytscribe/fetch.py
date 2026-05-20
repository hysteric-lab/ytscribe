"""Manifest-driven batch fetch. Per-video exception isolation (spec §7)."""
from __future__ import annotations

from pathlib import Path

from ytscribe.manifest import Manifest, VideoEntry
from ytscribe.output import write_output


def run_fetch(manifest: Manifest, out_dir: Path, fmt: str,
              caption_fn, asr_fn, manifest_path: Path | None = None) -> None:
    """Process every pending entry. One video's failure never aborts the batch.

    caption_fn / asr_fn: callables taking a VideoEntry, returning a Transcript.
    """
    for entry in manifest.pending():
        try:
            if entry.planned_action == "skip":
                entry.status = "done"
            else:
                fn = caption_fn if entry.planned_action == "caption" else asr_fn
                transcript = fn(entry)
                path = write_output(transcript, out_dir, fmt)
                entry.output_path = str(path)
                entry.status = "done"
        except Exception as exc:  # exception isolation — never kill the batch
            entry.status = "failed"
            entry.error = f"{type(exc).__name__}: {exc}"
        finally:
            if manifest_path is not None:
                manifest.save(manifest_path)  # persist progress for resume
