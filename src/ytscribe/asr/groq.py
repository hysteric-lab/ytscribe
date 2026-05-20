"""Cloud ASR via Groq Whisper. Needs GROQ_API_KEY."""
from __future__ import annotations

import os
from pathlib import Path

from ytscribe.config import Config
from ytscribe.models import Transcript


class GroqWhisper:
    def __init__(self, config: Config):
        self._config = config

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> Transcript:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        with open(audio_path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                file=(Path(audio_path).name, fh),
                model="whisper-large-v3",
                language=language_hint,
                response_format="text",
            )
        text = resp if isinstance(resp, str) else resp.text
        return Transcript.from_plain_text(Path(audio_path).stem,
                                          language_hint or "", text)
