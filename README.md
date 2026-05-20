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

## How it works

`scan` resolves the input and writes `manifest.json` — a per-video report of
caption availability and the planned action. Nothing is downloaded; this is
free. The summary tells you `have_caption` vs `need_asr` *before* you commit.

`fetch` consumes the manifest: captioned videos get their caption track,
caption-less videos go through ASR (default: local faster-whisper; set
`YTSCRIBE_ASR_PROVIDER=groq` or `openai` for cloud). Failures are isolated
per-video and recorded in the manifest — the batch always finishes.

## Configuration (environment variables)

| Var | Default | Meaning |
|-----|---------|---------|
| `YTSCRIBE_ASR_PROVIDER` | `local` | `local` / `groq` / `openai` |
| `YTSCRIBE_DOWNLOAD_TIMEOUT` | `300` | per-video audio download timeout (s) |
| `YTSCRIBE_PROBE_TIMEOUT` | `30` | per-video metadata probe timeout (s) |
| `YTSCRIBE_WHISPER_MODEL` | `large-v3` | faster-whisper model for local ASR |
