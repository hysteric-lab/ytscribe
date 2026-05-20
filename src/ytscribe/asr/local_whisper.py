"""Local ASR via faster-whisper. Model is loaded lazily on first transcribe()."""
from __future__ import annotations

from pathlib import Path

from ytscribe.config import Config
from ytscribe.models import Segment, Transcript


class LocalWhisper:
    def __init__(self, config: Config):
        self._config = config
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._config.whisper_model)
        return self._model

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> Transcript:
        model = self._ensure_model()
        segments, info = model.transcribe(str(audio_path), language=language_hint)
        segs = [Segment(s.start, s.end, s.text.strip()) for s in segments]
        return Transcript(Path(audio_path).stem, info.language, segs)
