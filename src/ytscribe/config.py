"""Engine configuration with environment overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(env: dict, key: str, default: int) -> int:
    try:
        return int(env[key])
    except (KeyError, ValueError):
        return default


@dataclass
class Config:
    asr_provider: str = "local"        # "local" | "groq" | "openai"
    download_timeout_s: int = 300
    probe_timeout_s: int = 30
    whisper_model: str = "large-v3"

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = os.environ if env is None else env
        return cls(
            asr_provider=env.get("YTSCRIBE_ASR_PROVIDER", "local"),
            download_timeout_s=_int_env(env, "YTSCRIBE_DOWNLOAD_TIMEOUT", 300),
            probe_timeout_s=_int_env(env, "YTSCRIBE_PROBE_TIMEOUT", 30),
            whisper_model=env.get("YTSCRIBE_WHISPER_MODEL", "large-v3"),
        )
