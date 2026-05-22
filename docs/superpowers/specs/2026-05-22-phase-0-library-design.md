# Phase 0 — ytscribe Engine Repo Design

> **Date**: 2026-05-22
> **Status**: Approved (brainstorming → ready for writing-plans)
> **Scope**: ytscribe engine repo (the open-source Apache-2.0 library), Phase 0 work items C2 / C3 / C6
> **Source of requirements**: `STRATEGY-2026-05-21.md` §3 (gap list) and §6 (Phase 0, Week 0, 2026-05-21 ~ 05-24)

## 1. Context

Phase 0 is the 4-day "launch blocker clearance" window. Three of its work items
land in the engine repo (the library); the other two (C1 bundle sweeper, C4
`/health` endpoint) belong to the private service repo and are out of scope here.

The three library work items:

- **C2 — Cookies + proxy injection.** YouTube blocks datacenter IPs. The engine
  currently passes nothing to `yt-dlp` for authentication or proxying, so the
  first large scan on a VPS will collect 429s. The library must accept a cookies
  file path and a proxy URL and forward them to every `yt-dlp` invocation.
- **C3 — Structured logging.** `grep -rn "logger\|logging" src/` returns zero
  hits. With no logs, the first stuck scan / crashed worker / `yt-dlp` error
  leaves no trace. The library must emit one structured (JSON-friendly) log
  record per subprocess call covering entry / exit / error.
- **C6 — CI.** The 82/82 test suite only runs on the author's laptop. The
  library needs a GitHub Actions workflow that runs the test matrix on every
  push and pull request.

## 2. Decisions Summary

| # | Decision | Choice |
|---|----------|--------|
| Q1 | How to handle the C2/C3 overlap on the 4 `yt-dlp` call sites | Shared `run_ytdlp()` wrapper |
| Q2 | Where the JSON formatter setup lives | Library exports an opt-in `setup_logging()` helper |
| Q3 | Behavior when `YTSCRIBE_COOKIES_FILE` is set but invalid | Fail-fast at config load |
| Q4 | CI workflow scope | pytest matrix only (ruff / mypy deferred to Phase 1) |

The four `yt-dlp` call sites are: `sources.py:28`, `probe.py:17`,
`captions.py:46`, `audio.py:10`. (Strategy text says "three"; there are four.)

## 3. Block 1 — `run_ytdlp()` wrapper (C2 + C3)

C2 and C3 both have to touch the same four call sites, so they are implemented
as one change: a single internal wrapper that owns command construction,
cookies/proxy injection, timing, and structured logging.

### 3.1 New module

`src/ytscribe/_ytdlp.py` — the leading underscore marks it internal-only; it is
not part of the public API and consumers must not import it.

```
run_ytdlp(
    args: Sequence[str],
    *,
    timeout_s: int,
    cookies_file: str | None,
    proxy: str | None,
    log_event: str,
) -> subprocess.CompletedProcess
```

Responsibilities:

1. **Command construction.** The wrapper owns the `yt-dlp` executable token;
   `args` is everything *after* it (so callers never pass `"yt-dlp"`
   themselves). Build the final command list as `["yt-dlp", <cookies/proxy
   flags>, *args]`: prepend `--cookies <cookies_file>` when `cookies_file` is
   set and `--proxy <proxy>` when `proxy` is set.
2. **Execution.** Run the subprocess with `capture_output=True`, `text=True`,
   `timeout=timeout_s`, and **always `check=False`** (see §3.3).
3. **Timing + structured logging** (see §3.2).
4. Return the `CompletedProcess` to the caller unmodified.

### 3.2 Logging contract

A single logger, `ytscribe.ytdlp`. The log schema is defined once here and
inherited by all four call sites — this prevents field-name drift (e.g. one site
emitting `duration`, another `elapsed_ms`).

- **Every call** emits one `INFO` record with `extra` fields:
  `event` (the caller-supplied `log_event`), `duration_ms`, `exit_code`,
  `cookies_used` (bool), `proxy_used` (bool), and `ytdlp_args` (the redacted
  command list — see below).
- **On non-zero exit code**, the wrapper emits a *second* record at `WARN`
  level with two additional `extra` fields: `stderr_tail` (last 500 characters
  of stderr) and `stdout_tail` (last 200 characters of stdout). Rationale: a log
  that says `{event, exit_code: 1, duration_ms}` tells the operator a call
  failed but not *why*; the tails carry the `yt-dlp` error text. 500/200 are
  empirical — `yt-dlp` failure messages are typically 200-400 chars, and stdout
  is usually empty on failure so 200 is a safety net.
- **On timeout**, the wrapper emits a `WARN` record *before* re-raising
  `subprocess.TimeoutExpired`. Because a timed-out process is killed before it
  exits, this record has its own schema — distinct from the success and
  non-zero-exit records:
  - `event`, `cookies_used`, `proxy_used`, `ytdlp_args` — same as the `INFO` record.
  - `duration_ms` ≈ `timeout_s`.
  - `timed_out: true` — a new boolean, absent from the success and
    non-zero-exit records. This is the key field: consumers split timeout from
    exit-failure on one boolean, rather than on the weak signal of "is
    `exit_code` null or non-zero". A Loki / Honeycomb alert for
    `exit_code != 0` would otherwise miss every timeout (those records have no
    `exit_code` field at all).
  - `exit_code: null` — the process never reached an exit.
  - `stderr_tail` / `stdout_tail` — best-effort from the `TimeoutExpired`
    exception's captured streams; may be empty (stdlib stream-capture behavior
    on timeout varies by version).

  The four call sites already have per-site `TimeoutExpired` handling;
  re-raising keeps that behavior unchanged.

**The `ytdlp_args` field name.** This field is named `ytdlp_args`, not `args`:
`args` is a reserved attribute on `logging.LogRecord`, and passing
`extra={"args": ...}` raises `KeyError` on the first call. `ytdlp_args` is also
the clearer name in a log aggregator, where a bare `args` could mean anything.

**Argument redaction.** All `ytdlp_args` tokens are logged verbatim except: the
token following `--cookies` is replaced with the literal `<redacted>`, and the
token following `--proxy` with the literal `<set>`. Rationale: the cookies file
path and proxy URL are not secrets but are operational surface that should not
leak through log aggregators (Loki / Honeycomb). The video URL and `yt-dlp`
flags themselves are not operational surface and are kept verbatim — they are
needed to debug which site / call produced the log entry. Implementation: scan
the command list, replace the token after `--cookies` and the token after
`--proxy`, leave everything else untouched (~10 lines, and it cannot drift
across the four call sites the way a positional rule could).

### 3.3 `check=False` is the wrapper's policy

The wrapper always runs with `check=False` and never decides exit-code
semantics — that is the caller's policy decision. Today
`audio.py::_default_runner` is the one site using `check=True`; it changes to
call the wrapper, receive the `CompletedProcess`, and raise on a non-zero
`returncode` itself. The wrapper's job is "run the subprocess and log it",
nothing more.

### 3.4 Call-site rewrite — DI seams unchanged

`sources.py`, `probe.py`, `captions.py`, and `audio.py` each already expose a
runner dependency-injection seam (`runner=_default_runner`,
`metadata_fetcher=_make_default_fetcher(timeout)`, `downloader=_default_downloader`,
`runner=_default_runner`). The wrapper sits *beneath* those seams: each existing
`_default_*` becomes essentially a one-line call to `run_ytdlp(...)`.

The public injection signatures (`runner=`, `metadata_fetcher=`, `downloader=`)
**do not change**. Existing tests inject at the `_default_*` layer, not at the
`yt-dlp` shell below it, so all 12 existing test modules keep passing. This is
the key invariant that makes a four-file change low-risk.

**Config threading.** The wrapper needs `cookies_file` and `proxy`, which live
on `Config`. `probe.py` already receives a `Config`; the other three sites do
not. Each site follows the factory pattern `probe.py` already uses
(`_make_default_fetcher`): the bare `_default_*` becomes a
`_make_default_*(config)` factory, and each public function (`resolve`,
`fetch_caption`, `download_audio`) gains an optional `config: Config | None =
None` keyword that defaults to `Config.from_env()`. This is additive — the
`runner=` / `downloader=` seam is untouched, and no existing test references a
`_default_*` symbol.

## 4. Block 2 — `Config` extension (C2)

`Config` is an existing `@dataclass` in `src/ytscribe/config.py`. Its `from_env`
classmethod already exists (introduced in commit `5c1c8da`). This work
**extends** both — it does not create a new dataclass or a new classmethod.

- **Two new fields** on `Config`: `cookies_file: str | None = None` and
  `proxy: str | None = None`.
- **`from_env` gains a validation branch** that reads `YTSCRIBE_COOKIES_FILE`
  and `YTSCRIBE_PROXY`.

### 4.1 `YTSCRIBE_COOKIES_FILE` — fail-fast at config load

An environment variable is an active declaration. Setting
`YTSCRIBE_COOKIES_FILE` tells the library "I want to use cookies", and the only
valid responses are "found it" or "I cannot, stopping and telling you" — never
"I cannot, but I will pretend otherwise and run anonymously".

Two constraints keep fail-fast from becoming a tyrant:

- **Constraint 1 — validate only when the variable is set.** An unset variable
  means "I do not want cookies", a legitimate anonymous-mode declaration that
  triggers no validation.
- **Constraint 2 — validation depth stops at "file exists + readable".** Check
  `Path(...).is_file()` and `os.access(path, os.R_OK)`. Do **not** parse the
  Netscape cookies.txt format — content can be refreshed by a host-side cron
  minutes after the check (the youtube/ repo runs a 24h refresh cycle), so
  content validation is both unreliable and at odds with TTL rotation. A
  syntactically broken cookies file is rejected by `yt-dlp` on first call and
  surfaces through the wrapper's structured log. Validation catches "set but
  empty", not "set but dirty".

On failure, raise `FileNotFoundError` (missing) or `PermissionError`
(unreadable). The message **must** contain the offending path and an explicit
fix hint (unset the variable, or point it at a readable file), so on-call
engineers never have to read the source.

### 4.2 `YTSCRIBE_PROXY` — verify on first use

`from_env` records the proxy string and does **not** validate it. Proxy
validation needs a network round-trip — too slow and too flaky (a transient DNS
hiccup should not block worker startup) for config load. A bad proxy fails on
the first `run_ytdlp()` call, and `yt-dlp`'s stderr is captured by the wrapper's
structured log.

Principle: cheap-to-validate checks run at config load; expensive-to-validate
checks run at first use.

## 5. Block 3 — `setup_logging()` helper (C3)

### 5.1 New module, public API

`src/ytscribe/logging_setup.py`, with `setup_logging` re-exported from
`src/ytscribe/__init__.py`. It is a public API, so it does **not** live in the
underscore-prefixed `_ytdlp.py` — that would contradict the "do not import me"
contract the underscore signals to consumers.

```
setup_logging(level: int = logging.INFO, stream: TextIO | None = None) -> None
```

### 5.2 Constraints (non-negotiable for implementation)

1. **Touch only the library's namespace.** Configure
   `logging.getLogger("ytscribe")` and its children — never the root logger.
   Set `propagate = False` on the `ytscribe` logger so a host application's root
   handler does not emit a duplicate line.
2. **`stream` defaults to `sys.stderr`.** Logs go to stderr by convention;
   stdout is reserved for program output. An explicit parameter lets the service
   pass its own stream (e.g. to route everything to stdout for `docker logs`).
3. **Idempotent.** A repeated call must not stack handlers — return early if a
   `JsonFormatter` handler is already attached. Protects against a service
   importing the library twice, or a test fixture calling it repeatedly.
   First-call-wins is intentional: to change `stream` or `level` mid-process, a
   caller must clear the `ytscribe` logger's handlers first.
4. **`python-json-logger` is an optional dependency.** Add to
   `pyproject.toml`: `json-logs = ["python-json-logger>=2.0"]` under
   `[project.optional-dependencies]`. `setup_logging()` does
   `try: from pythonjsonlogger import jsonlogger except ImportError: raise
   ImportError("install ytscribe[json-logs] to enable JSON logging")`. The
   library's core dependency stays a single package (`yt-dlp`).
5. **CLI opt-in via environment variable.** `cli.py::main` calls
   `setup_logging()` only when `os.environ.get("YTSCRIBE_LOG_FORMAT") == "json"`.
   Default off — a human running the CLI in a terminal should not see JSON. The
   service sets `YTSCRIBE_LOG_FORMAT=json` in its docker entrypoint.

### 5.3 `dev` extra also gains `python-json-logger`

`python-json-logger>=2.0` is added to the existing `dev` extra
(`dev = ["pytest>=8.0", "faster-whisper>=1.0.0", "python-json-logger>=2.0"]`) in
addition to the `json-logs` extra. This keeps `json-logs` as the user-facing
opt-in extra while letting CI's `pip install -e ".[dev]"` exercise
`test_logging_setup.py`. Without this, the logging contract would be untested in
CI.

## 6. Block 4 — CI workflow (C6)

A single file, `.github/workflows/test.yml`. Named `test.yml` (describes what it
does — runs tests), not `ci.yml` (describes what it is). Phase 1's lint and
release workflows will be `lint.yml` and `release.yml` — one concern per file.

- **Triggers**: `push` on `branches: [master]` and `pull_request`. **No
  `tags:`** trigger — tag-driven release (build wheel, publish PyPI, create
  GitHub release) is a separate Phase 1 `release.yml`.
- **Matrix**: `python-version: ["3.11", "3.12"]`, `fail-fast: false` (so one
  failing cell does not mask the other's signal). No 3.10 (`requires-python =
  ">=3.11"`), no 3.13 (faster-whisper / groq / yt-dlp 3.13 compatibility is
  still unsettled — adding it now invites flaky CI).
- **Steps**:
  1. `actions/checkout@v4`
  2. `actions/setup-python@v5` with `python-version: ${{ matrix.python-version }}`
     and `cache: pip` (non-negotiable — without it each run spends ~90s
     reinstalling the faster-whisper CUDA wheel variant; with it, ~10s)
  3. `pip install -e ".[dev]"` (editable install, so a later coverage step or a
     `test_helpers` import does not hit module-resolution issues)
  4. `pytest -q -m "not integration"` (non-negotiable — `tests/test_integration.py`
     carries the `integration` marker and needs real network plus a Groq API
     key; CI must not and cannot run it)

## 7. Testing

New and modified tests, all landing in the Phase 0 PR:

- **`tests/test_config.py`** (modify) — three contract tests that lock the
  fail-fast behavior so no future refactor silently downgrades it to
  warn-and-continue:
  - `test_config_fails_fast_on_missing_cookies_file` — `FileNotFoundError`
    raised, message matches `YTSCRIBE_COOKIES_FILE`.
  - `test_config_accepts_existing_cookies_file` — a real file is accepted and
    `cfg.cookies_file` is set.
  - `test_config_no_cookies_when_env_unset` — empty env yields
    `cfg.cookies_file is None`.
- **`tests/test_ytdlp.py`** (new) — `run_ytdlp` builds the command with
  `--cookies` / `--proxy` correctly when set and omits them when not; emits the
  expected `INFO` record; emits the second `WARN` record with `stderr_tail` on
  non-zero exit; redacts cookies path and proxy URL in the `ytdlp_args` field.
- **`tests/test_logging_setup.py`** (new) — `setup_logging` is idempotent;
  sets `propagate = False`; raises a clear `ImportError` when the `json-logs`
  extra is absent.

The existing 12 test modules must continue to pass unchanged — verified by the
DI-seam invariant in §3.4.

## 8. File Manifest

**New files:**

- `src/ytscribe/_ytdlp.py`
- `src/ytscribe/logging_setup.py`
- `.github/workflows/test.yml`
- `tests/test_ytdlp.py`
- `tests/test_logging_setup.py`

**Modified files:**

- `src/ytscribe/config.py` — two new `Config` fields, extended `from_env`
- `src/ytscribe/sources.py` — `_default_runner` calls `run_ytdlp`
- `src/ytscribe/probe.py` — default fetcher calls `run_ytdlp`
- `src/ytscribe/captions.py` — default runner calls `run_ytdlp`
- `src/ytscribe/audio.py` — `_default_runner` calls `run_ytdlp`, raises on
  non-zero `returncode` itself
- `src/ytscribe/cli.py` — opt-in `setup_logging()` call gated on
  `YTSCRIBE_LOG_FORMAT`
- `src/ytscribe/__init__.py` — re-export `setup_logging`
- `pyproject.toml` — `json-logs` optional extra; `python-json-logger` added to
  `dev` extra
- `tests/test_config.py` — three new contract tests

## 9. Deferred to Phase 1

Recorded here (not as comments in the workflow YAML — that is an anti-pattern):

- `ruff check` + `ruff format` — a single lint job in `lint.yml`, runs on 3.11
  only, no matrix needed.
- Coverage report + Codecov badge — if an OSS quality signal is wanted.
- A docker build smoke test — verify the Dockerfile builds on a GitHub runner.
- Tag-triggered `release.yml` — build wheel, publish to PyPI, create GitHub
  release.
- `mypy` — last, and only after type hints are filled in; the codebase has type
  hints but has never been run under mypy strict mode.

## 10. Acceptance Criteria

From `STRATEGY-2026-05-21.md` §6, the library's contribution to the Phase 0
acceptance check:

- `docker compose logs` shows JSON when the service runs the library with
  `YTSCRIBE_LOG_FORMAT=json`.
- A scan completes with cookies and (optionally) a proxy in effect.
- CI shows a green check on GitHub for both the 3.11 and 3.12 matrix cells.

## 11. Non-Goals

Per `STRATEGY-2026-05-21.md` §6 ("不該做的") and §9:

- Do not rewrite `engine.py`'s subprocess-to-CLI call (M2 — Phase 2).
- Do not touch worker concurrency.
- Do not add lint / type-check gates (Phase 1).
- Do not validate cookies *content* or proxy *reachability* at config load.
- `YTSCRIBE_PROXY` applies to `yt-dlp` (the YouTube IP-block problem) only — it
  is not wired into the ASR provider HTTP calls.
