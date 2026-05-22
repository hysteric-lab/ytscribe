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
    # is_file() and os.access() are separate syscalls; a tight race is
    # theoretically possible on network volumes. The consequence is a
    # misleading error from yt-dlp rather than from here — acceptable.
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
