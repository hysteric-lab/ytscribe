from ytscribe.fetch import run_fetch
from ytscribe.manifest import Manifest, VideoEntry
from ytscribe.models import Transcript


def _entry(vid, action):
    return VideoEntry(
        id=vid, title=vid, duration_s=60,
        captions={"manual": ["en"], "auto": []}, detected_language="en",
        planned_action=action, planned_reason="",
    )


def _ok_transcript(vid):
    return Transcript.from_plain_text(vid, "en", f"text for {vid}")


def test_caption_and_asr_entries_are_fetched(tmp_path):
    m = Manifest(source={}, scope={},
                 videos=[_entry("cap1", "caption"), _entry("asr1", "asr")])
    run_fetch(
        m, out_dir=tmp_path, fmt="txt",
        caption_fn=lambda e: _ok_transcript(e.id),
        asr_fn=lambda e: _ok_transcript(e.id),
    )
    assert all(v.status == "done" for v in m.videos)
    assert (tmp_path / "cap1.txt").exists()
    assert (tmp_path / "asr1.txt").exists()


def test_one_failure_does_not_kill_the_batch(tmp_path):
    m = Manifest(source={}, scope={},
                 videos=[_entry("good1", "asr"), _entry("bad", "asr"),
                         _entry("good2", "asr")])

    def asr_fn(entry):
        if entry.id == "bad":
            raise RuntimeError("simulated ASR failure")
        return _ok_transcript(entry.id)

    run_fetch(m, out_dir=tmp_path, fmt="txt",
              caption_fn=lambda e: _ok_transcript(e.id), asr_fn=asr_fn)

    statuses = {v.id: v.status for v in m.videos}
    assert statuses == {"good1": "done", "bad": "failed", "good2": "done"}
    bad = [v for v in m.videos if v.id == "bad"][0]
    assert "simulated ASR failure" in bad.error
    assert (tmp_path / "good2.txt").exists()  # batch continued past the failure


def test_skip_entries_are_left_alone(tmp_path):
    m = Manifest(source={}, scope={}, videos=[_entry("s", "skip")])
    run_fetch(m, out_dir=tmp_path, fmt="txt",
              caption_fn=lambda e: _ok_transcript(e.id),
              asr_fn=lambda e: _ok_transcript(e.id))
    assert m.videos[0].status == "done"
    assert m.videos[0].output_path is None
