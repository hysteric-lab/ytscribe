"""Resolve an input URL into a list of video IDs.

Harvest Scope rule (spec §2.1): only the /videos tab. Shorts (/shorts) and
Lives (/streams) are never resolved — channel URLs are coerced to /videos.
"""
from __future__ import annotations

from dataclasses import dataclass

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config


@dataclass
class ResolvedSource:
    url: str
    type: str            # "video" | "playlist" | "channel"
    video_ids: list[str]


def _classify(url: str) -> str:
    if "watch?v=" in url or url.startswith("https://youtu.be/"):
        return "video"
    if "playlist?list=" in url:
        return "playlist"
    return "channel"


def _make_default_runner(config: Config):
    """Build the default URL runner bound to a Config (cookies/proxy)."""
    def runner(url: str) -> str:
        proc = run_ytdlp(
            ["--flat-playlist", "--print", "id", url],
            timeout_s=120,
            cookies_file=config.cookies_file,
            proxy=config.proxy,
            log_event="sources.resolve",
        )
        return proc.stdout
    return runner


def resolve(url: str, runner=None, config: Config | None = None) -> ResolvedSource:
    src_type = _classify(url)
    if src_type == "video":
        if "watch?v=" in url:
            vid_id = url.split("watch?v=", 1)[1].split("&", 1)[0]
        else:  # youtu.be/
            vid_id = url.split("youtu.be/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        return ResolvedSource(url=url, type=src_type, video_ids=[vid_id])
    if runner is None:
        runner = _make_default_runner(config if config is not None else Config.from_env())
    scan_url = url
    if src_type == "channel" and not scan_url.rstrip("/").endswith("/videos"):
        scan_url = scan_url.rstrip("/") + "/videos"
    raw = runner(scan_url)
    ids = [line.strip() for line in raw.splitlines() if line.strip()]
    return ResolvedSource(url=url, type=src_type, video_ids=ids)
