from ytscribe.models import Segment, Transcript


def test_transcript_full_text_joins_segments():
    t = Transcript(
        video_id="abc12345678",
        language="en",
        segments=[Segment(0.0, 2.0, "Hello"), Segment(2.0, 4.0, "world")],
    )
    assert t.full_text == "Hello world"


def test_transcript_from_plain_text_makes_one_segment():
    t = Transcript.from_plain_text("abc12345678", "en", "just text")
    assert len(t.segments) == 1
    assert t.segments[0].text == "just text"
    assert t.full_text == "just text"
