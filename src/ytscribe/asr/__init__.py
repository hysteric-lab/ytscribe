"""Pluggable ASR provider interface."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ytscribe.config import Config
from ytscribe.models import Transcript


@runtime_checkable
class ASRProvider(Protocol):
    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> Transcript:
        ...


def get_provider(name: str, config: Config) -> ASRProvider:
    if name == "local":
        from ytscribe.asr.local_whisper import LocalWhisper
        return LocalWhisper(config)
    if name == "groq":
        from ytscribe.asr.groq import GroqWhisper
        return GroqWhisper(config)
    if name == "openai":
        from ytscribe.asr.openai import OpenAIWhisper
        return OpenAIWhisper(config)
    raise ValueError(f"unknown ASR provider: {name!r} (local|groq|openai)")
