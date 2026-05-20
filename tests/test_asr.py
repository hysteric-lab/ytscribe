import pytest

from ytscribe.asr import ASRProvider, get_provider
from ytscribe.config import Config
from ytscribe.models import Transcript


class FakeProvider:
    def transcribe(self, audio_path, language_hint=None) -> Transcript:
        return Transcript("vid12345678", language_hint or "en",
                          Transcript.from_plain_text("vid12345678", "en", "ok").segments)


def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeProvider(), ASRProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown ASR provider"):
        get_provider("nonsense", Config())


def test_get_provider_local_is_default():
    # constructing the provider object must not require the model to load
    p = get_provider("local", Config())
    assert hasattr(p, "transcribe")
