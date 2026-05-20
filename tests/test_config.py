from ytscribe.config import Config


def test_defaults():
    c = Config.from_env({})
    assert c.asr_provider == "local"
    assert c.download_timeout_s == 300
    assert c.probe_timeout_s == 30


def test_env_overrides():
    c = Config.from_env({
        "YTSCRIBE_ASR_PROVIDER": "groq",
        "YTSCRIBE_DOWNLOAD_TIMEOUT": "600",
    })
    assert c.asr_provider == "groq"
    assert c.download_timeout_s == 600
    assert c.probe_timeout_s == 30  # untouched


def test_invalid_timeout_falls_back_to_default():
    c = Config.from_env({"YTSCRIBE_DOWNLOAD_TIMEOUT": "not-a-number"})
    assert c.download_timeout_s == 300
