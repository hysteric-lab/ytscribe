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
