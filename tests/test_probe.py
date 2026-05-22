from ytscribe.probe import probe_videos


def fake_fetcher(vid):
    data = {
        "withcap": {"title": "Has caption", "duration": 120,
                    "subtitles": {"en": [{}]}, "automatic_captions": {},
                    "language": "en"},
        "nocap": {"title": "No caption", "duration": 90,
                  "subtitles": {}, "automatic_captions": {}, "language": "zh"},
        "broken": None,
    }
    return data[vid]


def test_video_with_caption_is_planned_caption():
    [e] = probe_videos(["withcap"], metadata_fetcher=fake_fetcher)
    assert e.planned_action == "caption"
    assert e.captions["manual"] == ["en"]


def test_video_without_caption_is_planned_asr():
    [e] = probe_videos(["nocap"], metadata_fetcher=fake_fetcher)
    assert e.planned_action == "asr"
    assert e.detected_language == "zh"


def test_unprobeable_video_is_skipped_not_fatal():
    entries = probe_videos(["withcap", "broken"], metadata_fetcher=fake_fetcher)
    assert len(entries) == 2
    broken = [e for e in entries if e.id == "broken"][0]
    assert broken.planned_action == "skip"
    assert broken.planned_reason == "unprobeable"


def test_probe_videos_accepts_config_alongside_injected_fetcher():
    from ytscribe.config import Config

    [e] = probe_videos(["withcap"], metadata_fetcher=fake_fetcher,
                       config=Config(probe_timeout_s=5))
    assert e.planned_action == "caption"


def test_default_fetcher_passes_cookies_and_proxy_to_wrapper(monkeypatch):
    import subprocess

    import ytscribe.probe as probe
    from ytscribe.config import Config

    seen = {}

    def fake_run_ytdlp(args, *, timeout_s, cookies_file, proxy, log_event):
        seen["cookies_file"] = cookies_file
        seen["proxy"] = proxy
        seen["timeout_s"] = timeout_s
        seen["log_event"] = log_event
        return subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0,
            stdout='{"title": "T", "duration": 1}', stderr="")

    monkeypatch.setattr(probe, "run_ytdlp", fake_run_ytdlp)
    fetcher = probe._make_default_fetcher(
        Config(probe_timeout_s=7, cookies_file="/c.txt", proxy="http://p:1"))
    meta = fetcher("vid12345678")
    assert meta == {"title": "T", "duration": 1}
    assert seen == {"cookies_file": "/c.txt", "proxy": "http://p:1",
                    "timeout_s": 7, "log_event": "probe.metadata"}
