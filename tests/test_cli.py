import ytscribe.cli as cli
from ytscribe.manifest import Manifest, VideoEntry


def _entry(vid, action="caption"):
    return VideoEntry(id=vid, title=vid, duration_s=60,
                      captions={"manual": ["en"], "auto": []},
                      detected_language="en", planned_action=action,
                      planned_reason="")


def test_scan_writes_manifest_and_prints_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan_to_manifest",
                        lambda url: Manifest(source={"url": url, "type": "video",
                                                     "resolved_count": 1},
                                             scope={}, videos=[_entry("a")]))
    mpath = tmp_path / "m.json"
    rc = cli.main(["scan", "https://youtu.be/a", "-o", str(mpath)])
    assert rc == 0
    assert mpath.exists()
    out = capsys.readouterr().out
    assert "have_caption" in out


def test_fetch_reads_manifest_and_processes(tmp_path, monkeypatch):
    m = Manifest(source={}, scope={}, videos=[_entry("a", "caption")])
    mpath = tmp_path / "m.json"
    m.save(mpath)
    monkeypatch.setattr(cli, "_make_caption_fn",
                        lambda cfg: (lambda e: __import__("ytscribe.models",
                            fromlist=["Transcript"]).Transcript.from_plain_text(
                            e.id, "en", "x")))
    rc = cli.main(["fetch", str(mpath), "-o", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out" / "a.txt").exists()


def test_unknown_command_returns_nonzero():
    assert cli.main(["bogus"]) != 0
