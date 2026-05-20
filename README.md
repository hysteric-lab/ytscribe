# ytscribe

YouTube transcription engine. Scan a channel/playlist/video to see what captions
exist *before* paying any download or ASR cost, then fetch.

## Install

    pip install -e ".[dev]"

## Use

    ytscribe scan "https://www.youtube.com/@channel" -o manifest.json
    ytscribe fetch manifest.json -o transcripts/
    ytscribe run "https://www.youtube.com/watch?v=ID" -o transcripts/

Only the `/videos` tab is scanned — Shorts and Lives are never harvested.
