import json

from ytscribe.models import Segment, Transcript
from ytscribe.output import render, write_output


def _t():
    return Transcript("vid12345678", "en",
                       [Segment(0.0, 1.5, "Hello"), Segment(1.5, 3.0, "world")])


def test_render_txt():
    assert render(_t(), "txt") == "Hello world"


def test_render_json_has_segments():
    doc = json.loads(render(_t(), "json"))
    assert doc["video_id"] == "vid12345678"
    assert len(doc["segments"]) == 2


def test_render_srt_has_timecodes():
    srt = render(_t(), "srt")
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "Hello" in srt


def test_write_output_creates_file(tmp_path):
    path = write_output(_t(), tmp_path, "txt")
    assert path.exists()
    assert path.name == "vid12345678.txt"
    assert path.read_text(encoding="utf-8") == "Hello world"
