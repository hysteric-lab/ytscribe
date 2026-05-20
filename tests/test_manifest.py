from ytscribe.manifest import Manifest, VideoEntry


def _entry(vid, action="caption"):
    return VideoEntry(
        id=vid, title=f"title {vid}", duration_s=60,
        captions={"manual": ["en"], "auto": []},
        detected_language="en", planned_action=action,
        planned_reason="manual caption available",
    )


def test_summary_counts_by_planned_action():
    m = Manifest(
        source={"url": "u", "type": "channel", "resolved_count": 3},
        scope={"included": "videos", "shorts_excluded": 5, "streams_excluded": 1},
        videos=[_entry("a", "caption"), _entry("b", "asr"), _entry("c", "asr")],
    )
    s = m.summary()
    assert s == {"total": 3, "have_caption": 1, "need_asr": 2, "skip": 0}


def test_manifest_json_round_trip(tmp_manifest_path):
    m = Manifest(
        source={"url": "u", "type": "video", "resolved_count": 1},
        scope={"included": "videos", "shorts_excluded": 0, "streams_excluded": 0},
        videos=[_entry("a")],
    )
    m.save(tmp_manifest_path)
    loaded = Manifest.load(tmp_manifest_path)
    assert loaded.videos[0].id == "a"
    assert loaded.summary() == m.summary()


def test_pending_entries_excludes_done():
    m = Manifest(source={}, scope={}, videos=[_entry("a"), _entry("b")])
    m.videos[0].status = "done"
    pending = m.pending()
    assert [e.id for e in pending] == ["b"]
