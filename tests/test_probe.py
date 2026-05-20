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
