from ytscribe.captions import clean_vtt, fetch_caption

SAMPLE_VTT = """WEBVTT

00:00:00.000 --> 00:00:02.000
Hello there

00:00:02.000 --> 00:00:04.000
general kenobi
"""


def test_clean_vtt_extracts_segments():
    segs = clean_vtt(SAMPLE_VTT)
    assert [s.text for s in segs] == ["Hello there", "general kenobi"]
    assert segs[0].start_s == 0.0
    assert segs[1].end_s == 4.0


def test_fetch_caption_returns_transcript():
    t = fetch_caption("vid12345678", "en", downloader=lambda v, l: SAMPLE_VTT)
    assert t.video_id == "vid12345678"
    assert t.language == "en"
    assert t.full_text == "Hello there general kenobi"


def test_fetch_caption_raises_when_empty():
    import pytest
    with pytest.raises(RuntimeError, match="no caption content"):
        fetch_caption("vid12345678", "en", downloader=lambda v, l: "")


def test_default_downloader_passes_cookies_and_proxy_to_wrapper(monkeypatch):
    import subprocess

    import ytscribe.captions as captions
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        seen["timeout_s"] = timeout_s
        seen["log_event"] = log_event
        return subprocess.CompletedProcess(args=["yt-dlp"], returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(captions, "run_ytdlp", fake_run_ytdlp)
    downloader = captions._make_default_downloader(
        Config(cookies_file="/c.txt", proxy="http://p:1"))
    result = downloader("vid12345678", "en")  # no VTT written -> empty string
    assert result == ""
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1",
                    "timeout_s": 120, "log_event": "captions.download"}
