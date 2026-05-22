import sys

import pytest

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


@pytest.mark.skipif(sys.platform == "win32",
                    reason="os.access does not reflect Unix permissions on Windows")
def test_config_fails_on_unreadable_cookies_file(tmp_path):
    restricted = tmp_path / "cookies.txt"
    restricted.write_text("")
    restricted.chmod(0o000)
    try:
        with pytest.raises(PermissionError, match="YTSCRIBE_COOKIES_FILE"):
            Config.from_env({"YTSCRIBE_COOKIES_FILE": str(restricted)})
    finally:
        restricted.chmod(0o644)  # restore so tmp_path cleanup works
