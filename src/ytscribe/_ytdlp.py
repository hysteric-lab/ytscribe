"""Internal: the single instrumented entry point for every yt-dlp subprocess.

Not part of the public API — the leading underscore signals "do not import me".
All four call sites (sources, probe, captions, audio) route through run_ytdlp so
cookies/proxy injection and the structured-log schema are defined exactly once.
"""
from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Sequence

logger = logging.getLogger("ytscribe.ytdlp")

_STDERR_TAIL = 500
_STDOUT_TAIL = 200


def _redact(cmd: Sequence[str]) -> list[str]:
    """Copy cmd with the token after --cookies / --proxy replaced.

    Cookies file paths and proxy URLs are operational surface that must not
    leak through log aggregators. Flags and the video URL are kept verbatim —
    they are needed to debug which call produced a log entry.
    """
    safe = list(cmd)
    for i in range(len(safe) - 1):
        if safe[i] == "--cookies":
            safe[i + 1] = "<redacted>"
        elif safe[i] == "--proxy":
            safe[i + 1] = "<set>"
    return safe


def _tail(stream: str | bytes | None, n: int) -> str:
    """Last n characters of a captured stream, best-effort (may be empty)."""
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        stream = stream.decode("utf-8", errors="replace")
    return stream[-n:]


def run_ytdlp(
    args: Sequence[str],
    *,
    timeout_s: int,
    cookies_file: str | None,
    proxy: str | None,
    log_event: str,
) -> subprocess.CompletedProcess:
    """Run yt-dlp with cookies/proxy injected and structured logging.

    `args` is everything after the yt-dlp executable token — callers never pass
    "yt-dlp" themselves. Always runs `check=False`: deciding what a non-zero
    exit code means is the caller's policy. On timeout, logs a WARN record then
    re-raises `subprocess.TimeoutExpired` so per-site timeout handling is
    unchanged.
    """
    cmd = ["yt-dlp"]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += list(args)

    base = {
        "event": log_event,
        "cookies_used": bool(cookies_file),
        "proxy_used": bool(proxy),
        "ytdlp_args": _redact(cmd),
    }
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("yt-dlp call timed out", extra={
            **base,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "timed_out": True,
            "exit_code": None,
            "stderr_tail": _tail(exc.stderr, _STDERR_TAIL),
            "stdout_tail": _tail(exc.stdout, _STDOUT_TAIL),
        })
        raise

    duration_ms = round((time.monotonic() - started) * 1000)
    logger.info("yt-dlp call complete", extra={
        **base, "duration_ms": duration_ms, "exit_code": proc.returncode,
    })
    if proc.returncode != 0:
        logger.warning("yt-dlp call failed", extra={
            **base,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "stderr_tail": _tail(proc.stderr, _STDERR_TAIL),
            "stdout_tail": _tail(proc.stdout, _STDOUT_TAIL),
        })
    return proc
