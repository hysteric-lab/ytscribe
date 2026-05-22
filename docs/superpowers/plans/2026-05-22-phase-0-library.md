# Phase 0 Engine Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ytscribe engine library survivable on a VPS — inject cookies/proxy into every yt-dlp call, emit structured JSON logs, and run the test suite in CI.

**Architecture:** All four yt-dlp call sites are routed through one internal `run_ytdlp()` wrapper that owns command construction, cookies/proxy injection, and structured logging. Cookies/proxy reach the wrapper via `Config`, threaded through each public function as an optional `config=` keyword while the existing dependency-injection seams (`runner=` / `metadata_fetcher=` / `downloader=`) stay byte-for-byte unchanged. An opt-in `setup_logging()` helper configures JSON output without the library ever touching logging on import. CI runs the pytest matrix on 3.11 and 3.12.

**Tech Stack:** Python 3.11+, `subprocess`, stdlib `logging`, `python-json-logger` (optional extra), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-22-phase-0-library-design.md` (commit `02ed3a5`).

---

## Implementation Notes (read before starting)

Two clarifications discovered during planning — both mechanical, neither changes the approved architecture:

1. **`ytdlp_args`, not `args`.** `logging.LogRecord` reserves the attribute name `args`; passing `extra={"args": ...}` raises `KeyError` on the first call. The structured-log field is therefore named `ytdlp_args` end-to-end. (The spec §3.2 calls it `args`; `ytdlp_args` is also the better Loki/Honeycomb query name.)
2. **Config threading via factory closures.** The wrapper takes `cookies_file` / `proxy` as explicit keyword arguments. Three of the four call sites currently receive no `Config`. This plan follows the pattern `probe.py` already uses (`_make_default_fetcher`): each site replaces its bare `_default_*` function with a `_make_default_*(config)` factory, and each public function gains an optional `config: Config | None = None` keyword that defaults to `Config.from_env()`. No existing test references a `_default_*` symbol, so this breaks nothing.

## Setup — branch

- [ ] Create the working branch:

```bash
cd ~/vs/projects/ytscribe/ytscribe
git checkout -b phase-0-library
```

---

## Task 1: Config — cookies/proxy fields with fail-fast validation

**Files:**
- Modify: `src/ytscribe/config.py` (full rewrite — 31-line file)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add `import pytest` at the top of `tests/test_config.py`, then append:

```python
def test_config_fails_fast_on_missing_cookies_file(tmp_path):
    bad = str(tmp_path / "nonexistent.txt")
    with pytest.raises(FileNotFoundError, match="YTSCRIBE_COOKIES_FILE"):
        Config.from_env({"YTSCRIBE_COOKIES_FILE": bad})


def test_config_accepts_existing_cookies_file(tmp_path):
    good = tmp_path / "cookies.txt"
    good.write_text("# Netscape HTTP Cookie File\n")
    cfg = Config.from_env({"YTSCRIBE_COOKIES_FILE": str(good)})
    assert cfg.cookies_file == str(good)


def test_config_no_cookies_when_env_unset():
    cfg = Config.from_env({})
    assert cfg.cookies_file is None
    assert cfg.proxy is None


def test_config_records_proxy_without_validation():
    cfg = Config.from_env({"YTSCRIBE_PROXY": "http://does-not-resolve.invalid:9999"})
    assert cfg.proxy == "http://does-not-resolve.invalid:9999"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_config.py`
Expected: FAIL — `AttributeError`/`TypeError` (no `cookies_file` attribute, `from_env` does not validate).

- [ ] **Step 3: Rewrite `src/ytscribe/config.py`**

```python
"""Engine configuration with environment overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(env: dict, key: str, default: int) -> int:
    try:
        return int(env[key])
    except (KeyError, ValueError):
        return default


def _resolve_cookies_file(env: dict) -> str | None:
    """Read YTSCRIBE_COOKIES_FILE; fail fast if it is set but unusable.

    Unset means "run anonymously" — a legitimate declaration, validated as None.
    When set, the file must exist and be readable. Content is not inspected:
    a syntactically broken cookies file is rejected by yt-dlp on first call and
    surfaces through the structured log.
    """
    cookies_file = env.get("YTSCRIBE_COOKIES_FILE")
    if cookies_file is None:
        return None
    path = Path(cookies_file)
    if not path.is_file():
        raise FileNotFoundError(
            f"YTSCRIBE_COOKIES_FILE={cookies_file!r} does not exist or is not a file. "
            f"Unset the env var to run without cookies, or point it at a readable cookies.txt."
        )
    if not os.access(path, os.R_OK):
        raise PermissionError(
            f"YTSCRIBE_COOKIES_FILE={cookies_file!r} exists but is not readable. "
            f"Check ownership / permissions."
        )
    return cookies_file


@dataclass
class Config:
    asr_provider: str = "local"        # "local" | "groq" | "openai"
    download_timeout_s: int = 300
    probe_timeout_s: int = 30
    whisper_model: str = "large-v3"
    cookies_file: str | None = None
    proxy: str | None = None

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = os.environ if env is None else env
        return cls(
            asr_provider=env.get("YTSCRIBE_ASR_PROVIDER", "local"),
            download_timeout_s=_int_env(env, "YTSCRIBE_DOWNLOAD_TIMEOUT", 300),
            probe_timeout_s=_int_env(env, "YTSCRIBE_PROBE_TIMEOUT", 30),
            whisper_model=env.get("YTSCRIBE_WHISPER_MODEL", "large-v3"),
            cookies_file=_resolve_cookies_file(env),
            proxy=env.get("YTSCRIBE_PROXY"),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_config.py`
Expected: PASS — all 7 tests (3 original + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/config.py tests/test_config.py
git commit -m "feat: add cookies/proxy config with fail-fast validation"
```

---

## Task 2: `run_ytdlp()` wrapper

**Files:**
- Create: `src/ytscribe/_ytdlp.py`
- Test: `tests/test_ytdlp.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ytdlp.py`:

```python
import logging
import subprocess

import pytest

from ytscribe import _ytdlp


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_ytdlp_injects_cookies_and_proxy(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed()

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    _ytdlp.run_ytdlp(["-J", "https://youtu.be/x"], timeout_s=30,
                     cookies_file="/data/cookies.txt", proxy="http://p:1",
                     log_event="probe.metadata")
    assert captured["cmd"] == [
        "yt-dlp", "--cookies", "/data/cookies.txt", "--proxy", "http://p:1",
        "-J", "https://youtu.be/x"]


def test_run_ytdlp_omits_flags_when_unset(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed()

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None, proxy=None,
                     log_event="probe.metadata")
    assert captured["cmd"] == ["yt-dlp", "-J", "x"]


def test_run_ytdlp_redacts_cookies_and_proxy_in_log(monkeypatch, caplog):
    monkeypatch.setattr(_ytdlp.subprocess, "run",
                        lambda cmd, **kw: _completed())
    with caplog.at_level(logging.INFO, logger="ytscribe.ytdlp"):
        _ytdlp.run_ytdlp(["-J", "https://youtu.be/x"], timeout_s=30,
                         cookies_file="/secret/cookies.txt",
                         proxy="http://user:pw@host:1", log_event="probe.metadata")
    record = caplog.records[-1]
    assert "/secret/cookies.txt" not in record.ytdlp_args
    assert "http://user:pw@host:1" not in record.ytdlp_args
    assert "<redacted>" in record.ytdlp_args
    assert "<set>" in record.ytdlp_args


def test_run_ytdlp_returns_nonzero_and_logs_warn_with_tails(monkeypatch, caplog):
    monkeypatch.setattr(
        _ytdlp.subprocess, "run",
        lambda cmd, **kw: _completed(returncode=1,
                                     stderr="ERROR: HTTP Error 429: Too Many Requests"))
    with caplog.at_level(logging.INFO, logger="ytscribe.ytdlp"):
        proc = _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None,
                                proxy=None, log_event="probe.metadata")
    assert proc.returncode == 1  # returned, never raised
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "429" in warnings[0].stderr_tail


def test_run_ytdlp_logs_timeout_and_reraises(monkeypatch, caplog):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    monkeypatch.setattr(_ytdlp.subprocess, "run", fake_run)
    with caplog.at_level(logging.WARNING, logger="ytscribe.ytdlp"):
        with pytest.raises(subprocess.TimeoutExpired):
            _ytdlp.run_ytdlp(["-J", "x"], timeout_s=30, cookies_file=None,
                             proxy=None, log_event="probe.metadata")
    record = caplog.records[-1]
    assert record.timed_out is True
    assert record.exit_code is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_ytdlp.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytscribe._ytdlp'`.

- [ ] **Step 3: Create `src/ytscribe/_ytdlp.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_ytdlp.py`
Expected: PASS — all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/_ytdlp.py tests/test_ytdlp.py
git commit -m "feat: add instrumented run_ytdlp wrapper"
```

---

## Task 3: `setup_logging()` helper

**Files:**
- Create: `src/ytscribe/logging_setup.py`
- Modify: `src/ytscribe/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_logging_setup.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Replace the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
local = ["faster-whisper>=1.0.0"]
groq = ["groq>=0.11.0"]
openai = ["openai>=1.40.0"]
```

...add `json-logs` and extend `dev` so the existing block becomes:

```toml
[project.optional-dependencies]
local = ["faster-whisper>=1.0.0"]
groq = ["groq>=0.11.0"]
openai = ["openai>=1.40.0"]
json-logs = ["python-json-logger>=2.0"]
dev = ["pytest>=8.0", "faster-whisper>=1.0.0", "python-json-logger>=2.0"]
```

Then install the new dev dependency into the working environment:

Run: `pip install -e ".[dev]"`
Expected: `python-json-logger` is installed.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_logging_setup.py`:

```python
import logging
import sys

import pytest

from ytscribe.logging_setup import setup_logging


def _clear():
    log = logging.getLogger("ytscribe")
    log.handlers.clear()
    log.propagate = True


def test_setup_logging_attaches_one_handler_and_disables_propagate():
    _clear()
    setup_logging()
    log = logging.getLogger("ytscribe")
    assert len(log.handlers) == 1
    assert log.propagate is False
    _clear()


def test_setup_logging_is_idempotent():
    _clear()
    setup_logging()
    setup_logging()
    setup_logging()
    assert len(logging.getLogger("ytscribe").handlers) == 1
    _clear()


def test_setup_logging_raises_clear_error_without_extra(monkeypatch):
    _clear()
    # None in sys.modules makes `import pythonjsonlogger` raise ImportError.
    monkeypatch.setitem(sys.modules, "pythonjsonlogger", None)
    with pytest.raises(ImportError, match="json-logs"):
        setup_logging()
    _clear()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest -q tests/test_logging_setup.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytscribe.logging_setup'`.

- [ ] **Step 4: Create `src/ytscribe/logging_setup.py`**

```python
"""Opt-in JSON logging configuration for the ytscribe namespace.

A library must never configure logging on import. This helper is opt-in: a
consumer (the CLI, the service worker) calls it explicitly. It touches only the
`ytscribe` logger and its children — never the root logger.
"""
from __future__ import annotations

import logging
import sys
from typing import TextIO

_LOGGER_NAME = "ytscribe"


def setup_logging(level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """Attach a JSON-formatted handler to the `ytscribe` logger.

    Idempotent — a repeated call is a no-op. First-call-wins is intentional: to
    change `stream` or `level` mid-process, a caller must clear the `ytscribe`
    logger's handlers first.

    Requires the `json-logs` extra (`pip install ytscribe[json-logs]`).
    """
    try:
        from pythonjsonlogger import jsonlogger
    except ImportError as exc:
        raise ImportError(
            "install ytscribe[json-logs] to enable JSON logging"
        ) from exc

    logger = logging.getLogger(_LOGGER_NAME)
    if any(isinstance(h.formatter, jsonlogger.JsonFormatter)
           for h in logger.handlers):
        return  # idempotent: already configured

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(
        jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
```

- [ ] **Step 5: Update `src/ytscribe/__init__.py`**

Replace the file contents:

```python
"""ytscribe — YouTube transcription engine."""
from ytscribe.logging_setup import setup_logging

__version__ = "0.1.0"

__all__ = ["setup_logging", "__version__"]
```

(`logging_setup` imports only stdlib at module level — the `python-json-logger`
import lives inside `setup_logging()` — so this adds no import-time cost and no
dependency on the `json-logs` extra just to import the package.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest -q tests/test_logging_setup.py`
Expected: PASS — all 3 tests.

- [ ] **Step 7: Commit**

```bash
git add src/ytscribe/logging_setup.py src/ytscribe/__init__.py pyproject.toml tests/test_logging_setup.py
git commit -m "feat: add opt-in setup_logging helper"
```

---

## Task 4: Route `sources.py` through the wrapper

**Files:**
- Modify: `src/ytscribe/sources.py` (full rewrite — 48-line file)
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sources.py`:

```python
def test_default_runner_passes_cookies_and_proxy_to_wrapper(monkeypatch):
    import ytscribe.sources as sources
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        import subprocess
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=0,
                                           stdout="aaaaaaaaaaa\n", stderr="")

    monkeypatch.setattr(sources, "run_ytdlp", fake_run_ytdlp)
    runner = sources._make_default_runner(Config(cookies_file="/c.txt", proxy="http://p:1"))
    out = runner("https://www.youtube.com/@chan/videos")
    assert out == "aaaaaaaaaaa\n"
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_sources.py::test_default_runner_passes_cookies_and_proxy_to_wrapper`
Expected: FAIL — `AttributeError: module 'ytscribe.sources' has no attribute '_make_default_runner'`.

- [ ] **Step 3: Rewrite `src/ytscribe/sources.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_sources.py`
Expected: PASS — all 5 tests (4 original + 1 new). The 4 original tests inject `runner=`, so they never build the default and never call `Config.from_env()`.

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/sources.py tests/test_sources.py
git commit -m "refactor: route sources.py through run_ytdlp wrapper"
```

---

## Task 5: Route `probe.py` through the wrapper

**Files:**
- Modify: `src/ytscribe/probe.py` (full rewrite — 69-line file)
- Test: `tests/test_probe.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_probe.py`:

```python
def test_default_fetcher_passes_cookies_and_proxy_to_wrapper(monkeypatch):
    import subprocess

    import ytscribe.probe as probe
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        seen["timeout_s"] = timeout_s
        return subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0,
            stdout='{"title": "T", "duration": 1}', stderr="")

    monkeypatch.setattr(probe, "run_ytdlp", fake_run_ytdlp)
    fetcher = probe._make_default_fetcher(
        Config(probe_timeout_s=7, cookies_file="/c.txt", proxy="http://p:1"))
    meta = fetcher("vid12345678")
    assert meta == {"title": "T", "duration": 1}
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1", "timeout_s": 7}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_probe.py::test_default_fetcher_passes_cookies_and_proxy_to_wrapper`
Expected: FAIL — `TypeError` (`_make_default_fetcher` takes an `int` timeout, not a `Config`).

- [ ] **Step 3: Rewrite `src/ytscribe/probe.py`**

The module-level `_default_fetcher = _make_default_fetcher()` line is removed: it
is unused (no file imports `ytscribe.probe._default_fetcher`), and keeping it
would call `Config.from_env()` at import time. The `DEFAULT_PROBE_TIMEOUT_S`
constant is removed for the same reason — it has no remaining reference.

```python
"""Probe videos for caption availability — the scan core. No downloads."""
from __future__ import annotations

import json
import subprocess

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config
from ytscribe.manifest import VideoEntry


def _make_default_fetcher(config: Config | None = None):
    """Build a yt-dlp metadata fetcher bound to a Config (timeout, cookies, proxy)."""
    if config is None:
        config = Config.from_env()

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
        metadata_fetcher = _make_default_fetcher(config)
    entries = []
    for vid in video_ids:
        meta = metadata_fetcher(vid)
        entries.append(_skipped_entry(vid) if meta is None
                       else _entry_from_metadata(vid, meta))
    return entries
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_probe.py`
Expected: PASS — all 5 tests (4 original + 1 new).

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/probe.py tests/test_probe.py
git commit -m "refactor: route probe.py through run_ytdlp wrapper"
```

---

## Task 6: Route `captions.py` through the wrapper

**Files:**
- Modify: `src/ytscribe/captions.py` (full rewrite — 64-line file)
- Test: `tests/test_captions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_captions.py`:

```python
def test_default_downloader_passes_cookies_and_proxy_to_wrapper(monkeypatch, tmp_path):
    import subprocess

    import ytscribe.captions as captions
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(captions, "run_ytdlp", fake_run_ytdlp)
    downloader = captions._make_default_downloader(
        Config(cookies_file="/c.txt", proxy="http://p:1"))
    result = downloader("vid12345678", "en")  # no VTT written -> empty string
    assert result == ""
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_captions.py::test_default_downloader_passes_cookies_and_proxy_to_wrapper`
Expected: FAIL — `AttributeError: module 'ytscribe.captions' has no attribute '_make_default_downloader'`.

- [ ] **Step 3: Rewrite `src/ytscribe/captions.py`**

```python
"""Fetch and clean existing YouTube caption tracks."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config
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


def _make_default_downloader(config: Config):
    """Build the default caption downloader bound to a Config (cookies/proxy)."""
    def downloader(video_id: str, lang: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cap"
            try:
                run_ytdlp(
                    ["--skip-download", "--write-subs", "--write-auto-subs",
                     "--sub-langs", lang, "--sub-format", "vtt",
                     "-o", str(out), f"https://www.youtube.com/watch?v={video_id}"],
                    timeout_s=120,
                    cookies_file=config.cookies_file,
                    proxy=config.proxy,
                    log_event="captions.download",
                )
            except subprocess.TimeoutExpired:
                return ""
            for f in sorted(Path(tmp).glob("cap*.vtt")):
                return f.read_text(encoding="utf-8")
        return ""
    return downloader


def fetch_caption(video_id: str, lang: str, downloader=None,
                  config: Config | None = None) -> Transcript:
    if downloader is None:
        downloader = _make_default_downloader(
            config if config is not None else Config.from_env())
    vtt = downloader(video_id, lang)
    segments = clean_vtt(vtt) if vtt else []
    if not segments:
        raise RuntimeError(f"no caption content for {video_id} ({lang})")
    return Transcript(video_id=video_id, language=lang, segments=segments)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_captions.py`
Expected: PASS — all 4 tests (3 original + 1 new).

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/captions.py tests/test_captions.py
git commit -m "refactor: route captions.py through run_ytdlp wrapper"
```

---

## Task 7: Route `audio.py` through the wrapper

**Files:**
- Modify: `src/ytscribe/audio.py` (full rewrite — 40-line file)
- Test: `tests/test_audio.py`

The adapter does **not** catch `TimeoutExpired` — the wrapper logs and re-raises
it, and the outer `download_audio` already handles it. On a non-zero exit code
the adapter raises `subprocess.CalledProcessError` itself (the wrapper runs
`check=False`), so `download_audio`'s existing `except CalledProcessError` still
fires.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_audio.py`:

```python
def test_default_runner_passes_cookies_and_proxy_to_wrapper(monkeypatch, tmp_path):
    import ytscribe.audio as audio
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(audio, "run_ytdlp", fake_run_ytdlp)
    runner = audio._make_default_runner(Config(cookies_file="/c.txt", proxy="http://p:1"))
    path = runner("vid12345678", tmp_path, timeout_s=300)
    assert path == tmp_path / "vid12345678.mp3"
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1"}


def test_default_runner_raises_called_process_error_on_nonzero(monkeypatch, tmp_path):
    import ytscribe.audio as audio
    from ytscribe.config import Config

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=1,
                                           stdout="", stderr="boom")

    monkeypatch.setattr(audio, "run_ytdlp", fake_run_ytdlp)
    runner = audio._make_default_runner(Config())
    with pytest.raises(subprocess.CalledProcessError):
        runner("vid12345678", tmp_path, timeout_s=300)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_audio.py::test_default_runner_passes_cookies_and_proxy_to_wrapper tests/test_audio.py::test_default_runner_raises_called_process_error_on_nonzero`
Expected: FAIL — `AttributeError: module 'ytscribe.audio' has no attribute '_make_default_runner'`.

- [ ] **Step 3: Rewrite `src/ytscribe/audio.py`**

```python
"""Download audio for ASR. Cleans stray partials on timeout, then raises."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ytscribe._ytdlp import run_ytdlp
from ytscribe.config import Config


def _make_default_runner(config: Config):
    """Build the default audio runner bound to a Config (cookies/proxy)."""
    def runner(video_id: str, out_dir: Path, timeout_s: int) -> Path:
        out_tmpl = str(Path(out_dir) / f"{video_id}.%(ext)s")
        proc = run_ytdlp(
            ["-x", "--audio-format", "mp3", "--audio-quality", "5",
             "-o", out_tmpl, f"https://www.youtube.com/watch?v={video_id}"],
            timeout_s=timeout_s,
            cookies_file=config.cookies_file,
            proxy=config.proxy,
            log_event="audio.download",
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, proc.args, output=proc.stdout, stderr=proc.stderr)
        return Path(out_dir) / f"{video_id}.mp3"
    return runner


def _clean_strays(video_id: str, out_dir: Path) -> None:
    for stray in Path(out_dir).glob(f"{video_id}.*"):
        try:
            stray.unlink()
        except OSError:
            pass


def download_audio(video_id: str, out_dir: Path, timeout_s: int,
                   runner=None, config: Config | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if runner is None:
        runner = _make_default_runner(config if config is not None else Config.from_env())
    try:
        return runner(video_id, out_dir, timeout_s)
    except subprocess.TimeoutExpired as exc:
        _clean_strays(video_id, out_dir)
        raise RuntimeError(
            f"audio download timeout for {video_id} after {timeout_s}s"
        ) from exc
    except subprocess.CalledProcessError as exc:
        _clean_strays(video_id, out_dir)
        raise RuntimeError(f"audio download failed for {video_id} (yt-dlp error)") from exc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_audio.py`
Expected: PASS — all 5 tests (3 original + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/ytscribe/audio.py tests/test_audio.py
git commit -m "refactor: route audio.py through run_ytdlp wrapper"
```

---

## Task 8: Thread Config and opt-in JSON logging through the CLI

**Files:**
- Modify: `src/ytscribe/cli.py`
- Test: `tests/test_cli.py` (no change — existing tests must still pass)

`_scan_to_manifest` keeps its one-argument signature (`test_cli.py` monkeypatches
it with a one-argument lambda). It builds `Config.from_env()` once and threads it
into `resolve` and `probe_videos` — and because it is the first thing each
command runs, cookies fail-fast fires at command start.

- [ ] **Step 1: Update the import block**

Replace lines 1-17 of `src/ytscribe/cli.py`:

```python
"""ytscribe command-line interface: scan / fetch / run."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from ytscribe.config import Config
from ytscribe.logging_setup import setup_logging
from ytscribe.manifest import Manifest
from ytscribe.probe import probe_videos
from ytscribe.sources import resolve
from ytscribe.fetch import run_fetch
from ytscribe.asr import get_provider
from ytscribe.audio import download_audio
from ytscribe.captions import fetch_caption
```

- [ ] **Step 2: Thread Config through `_scan_to_manifest`**

Replace the `_scan_to_manifest` function:

```python
def _scan_to_manifest(url: str) -> Manifest:
    config = Config.from_env()
    src = resolve(url, config=config)
    entries = probe_videos(src.video_ids, config=config)
    return Manifest(
        source={"url": url, "type": src.type, "resolved_count": len(src.video_ids)},
        scope={"included": "videos", "shorts_excluded": 0, "streams_excluded": 0},
        videos=entries,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )
```

- [ ] **Step 3: Thread Config into the caption and ASR closures**

Replace `_make_caption_fn` and `_make_asr_fn`:

```python
def _make_caption_fn(config: Config):
    def caption_fn(entry):
        langs = entry.captions["manual"] or entry.captions["auto"]
        return fetch_caption(entry.id, langs[0], config=config)
    return caption_fn


def _make_asr_fn(config: Config, work_dir: Path):
    provider = get_provider(config.asr_provider, config)

    def asr_fn(entry):
        audio = download_audio(entry.id, work_dir, config.download_timeout_s,
                               config=config)
        try:
            return provider.transcribe(audio, entry.detected_language or None)
        finally:
            audio.unlink(missing_ok=True)
    return asr_fn
```

- [ ] **Step 4: Add opt-in logging at the top of `main`**

Replace the first line of the `main` function body (`parser = argparse.ArgumentParser(prog="ytscribe")`) so the function begins:

```python
def main(argv: list[str] | None = None) -> int:
    if os.environ.get("YTSCRIBE_LOG_FORMAT") == "json":
        setup_logging()
    parser = argparse.ArgumentParser(prog="ytscribe")
```

(The rest of `main` is unchanged.)

- [ ] **Step 5: Run the full test suite to verify nothing broke**

Run: `pytest -q -m "not integration"`
Expected: PASS — every test, including the 3 `test_cli.py` tests. `test_cli.py` monkeypatches `_scan_to_manifest` (one-arg) and `_make_caption_fn` (one-arg); both signatures are preserved.

- [ ] **Step 6: Commit**

```bash
git add src/ytscribe/cli.py
git commit -m "feat: thread Config and opt-in JSON logging through CLI"
```

---

## Task 9: CI workflow

**Files:**
- Create: `.github/workflows/test.yml`

A workflow file cannot be unit-tested; it is verified by validating the YAML
locally and then observing a green check on GitHub after push.

- [ ] **Step 1: Create `.github/workflows/test.yml`**

```yaml
name: test

on:
  push:
    branches: [master]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: pytest -q -m "not integration"
```

- [ ] **Step 2: Validate the YAML locally**

Run: `python -c "import yaml, sys; yaml.safe_load(open('.github/workflows/test.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Run the exact CI command locally to confirm it is green**

Run: `pytest -q -m "not integration"`
Expected: PASS — the full suite (every test from Tasks 1-8).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add pytest matrix workflow"
```

- [ ] **Step 5: Push and verify the green check**

```bash
git push -u origin phase-0-library
```

Then open the GitHub Actions tab and confirm both matrix cells (3.11, 3.12) pass.
This is the C6 acceptance criterion.

---

## Done — Verification Checklist

- [ ] `pytest -q -m "not integration"` is green locally.
- [ ] `YTSCRIBE_COOKIES_FILE` pointed at a missing file raises `FileNotFoundError` at startup (manual check: `YTSCRIBE_COOKIES_FILE=/nope python -c "from ytscribe.config import Config; Config.from_env()"`).
- [ ] `YTSCRIBE_LOG_FORMAT=json ytscribe scan <url>` emits JSON log lines on stderr; without the env var, no JSON.
- [ ] GitHub Actions shows a green check on both 3.11 and 3.12.
- [ ] The four yt-dlp call sites (`sources`, `probe`, `captions`, `audio`) all route through `run_ytdlp`; `grep -rn "subprocess.run" src/` shows only `_ytdlp.py`.
