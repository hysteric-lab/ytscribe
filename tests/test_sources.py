from ytscribe.sources import ResolvedSource, resolve


def fake_runner(url):
    # one id per line, as yt-dlp --flat-playlist --print id produces
    return "aaaaaaaaaaa\nbbbbbbbbbbb\nccccccccccc\n"


def test_single_video_url_resolves_to_one_id():
    r = resolve("https://www.youtube.com/watch?v=aaaaaaaaaaa", runner=fake_runner)
    assert r.type == "video"
    assert r.video_ids == ["aaaaaaaaaaa"]


def test_channel_url_is_coerced_to_videos_tab():
    captured = {}

    def capture(url):
        captured["url"] = url
        return "aaaaaaaaaaa\n"

    resolve("https://www.youtube.com/@chan", runner=capture)
    assert captured["url"].endswith("/videos")


def test_channel_resolves_all_ids():
    r = resolve("https://www.youtube.com/@chan", runner=fake_runner)
    assert r.type == "channel"
    assert r.video_ids == ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]


def test_playlist_url_is_not_coerced():
    captured = {}

    def capture(url):
        captured["url"] = url
        return "aaaaaaaaaaa\n"

    resolve("https://www.youtube.com/playlist?list=PLxxxx", runner=capture)
    assert "/videos" not in captured["url"]
