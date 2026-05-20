"""ytscribe command-line interface: scan / fetch / run."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from ytscribe.config import Config
from ytscribe.manifest import Manifest
from ytscribe.probe import probe_videos
from ytscribe.sources import resolve
from ytscribe.fetch import run_fetch
from ytscribe.asr import get_provider
from ytscribe.audio import download_audio
from ytscribe.captions import fetch_caption


def _scan_to_manifest(url: str) -> Manifest:
    src = resolve(url)
    entries = probe_videos(src.video_ids)
    return Manifest(
        source={"url": url, "type": src.type, "resolved_count": len(src.video_ids)},
        scope={"included": "videos", "shorts_excluded": 0, "streams_excluded": 0},
        videos=entries,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )


def _make_caption_fn(config: Config):
    def caption_fn(entry):
        langs = entry.captions["manual"] or entry.captions["auto"]
        return fetch_caption(entry.id, langs[0])
    return caption_fn


def _make_asr_fn(config: Config, work_dir: Path):
    provider = get_provider(config.asr_provider, config)

    def asr_fn(entry):
        audio = download_audio(entry.id, work_dir, config.download_timeout_s)
        try:
            return provider.transcribe(audio, entry.detected_language or None)
        finally:
            audio.unlink(missing_ok=True)
    return asr_fn


def _print_summary(manifest: Manifest) -> None:
    print(json.dumps(manifest.summary(), indent=2))


def _cmd_scan(args) -> int:
    manifest = _scan_to_manifest(args.url)
    manifest.save(Path(args.output))
    _print_summary(manifest)
    print(f"manifest -> {args.output}")
    return 0


def _cmd_fetch(args) -> int:
    config = Config.from_env()
    manifest = Manifest.load(Path(args.manifest))
    out_dir = Path(args.output)
    work_dir = out_dir / ".work"
    run_fetch(
        manifest, out_dir=out_dir, fmt=args.format,
        caption_fn=_make_caption_fn(config),
        asr_fn=_make_asr_fn(config, work_dir),
        manifest_path=Path(args.manifest),
    )
    _print_summary(manifest)
    return 0


def _cmd_run(args) -> int:
    manifest = _scan_to_manifest(args.url)
    tmp_manifest = Path(args.output) / "manifest.json"
    tmp_manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(tmp_manifest)
    fetch_args = argparse.Namespace(
        manifest=str(tmp_manifest), output=args.output, format=args.format)
    return _cmd_fetch(fetch_args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ytscribe")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("url")
    p_scan.add_argument("-o", "--output", default="manifest.json")

    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("manifest")
    p_fetch.add_argument("-o", "--output", default="transcripts")
    p_fetch.add_argument("-f", "--format", default="txt", choices=["txt", "srt", "json"])

    p_run = sub.add_parser("run")
    p_run.add_argument("url")
    p_run.add_argument("-o", "--output", default="transcripts")
    p_run.add_argument("-f", "--format", default="txt", choices=["txt", "srt", "json"])

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "fetch":
        return _cmd_fetch(args)
    if args.command == "run":
        return _cmd_run(args)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
