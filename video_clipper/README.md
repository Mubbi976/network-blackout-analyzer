# Video Clipper

A local FastAPI application for processing YouTube media you are authorized to
use. It supports metadata/format discovery, background extraction and live
recording, timestamped OpenAI Whisper transcription, semantic moment ranking,
and FFmpeg vertical MP4 export.

Use only authorized sources and respect YouTube's terms, copyright, and access
controls. The application rejects non-YouTube URLs, does not authenticate to
private streams, bypass DRM, or retrieve unavailable historical live footage.

## Requirements

- Python 3.11+ (validated here with 3.12.10, 64-bit).
- FFmpeg and FFprobe installed separately from pip.
- Git.
- Node.js/npm are not required; the UI is local HTML/CSS/JavaScript.

In the current Windows environment: Python 3.12.10, Git 2.56.0, FFmpeg and
FFprobe 9.0.2 are installed. Node.js/npm are not installed.

### FFmpeg on Windows

FFmpeg is a separate system tool; Python package installation does not install
it. Install using Windows Package Manager:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Open a new PowerShell window and verify `ffmpeg -version` and
`ffprobe -version`. If not on `PATH`, configure full paths using `FFMPEG_PATH`
and `FFPROBE_PATH` in `.env`.

## Setup

From `video_clipper`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

The Whisper and sentence-transformer models are downloaded on their first use.
They run locally on CPU; model weights require additional disk space. The
included `.env.example` uses the `small` Whisper model. Set `WHISPER_MODEL=tiny`
for a smaller/faster first test.

## Launch

For one-click startup on Windows, double-click `Start-Video-Clipper.bat`. It
starts the local API if needed, waits for its health check, and opens the UI.
Keep the server console window open while using the app; close it to stop the
server.

To start it manually:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> for the UI, `/docs` for the interactive API, or
`/health` for the API health response. The app binds to localhost by default.

## Cloud deployment

The repository includes a Render Blueprint in `../render.yaml` and a production
`Dockerfile`. To create the hosted service, import this GitHub repository into
Render and deploy its Blueprint, or use the [one-click Render setup](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FMubbi976%2Fnetwork-blackout-analyzer).
The service uses a paid 1 CPU / 2 GB instance and a 25 GB persistent disk; the
Blueprint creates both. Cloud usage is billed by Render.

The container installs Python 3.12, CPU-only PyTorch, FFmpeg/FFprobe, and the
Python dependencies. Downloaded media, exports, SQLite job state, logs, and
AI model weights live on the mounted disk. The first transcription downloads
the `tiny` Whisper model into that disk. The deployment is intentionally a
single instance and one worker so local media files and SQLite state stay
consistent.

The Blueprint generates an `APP_ACCESS_TOKEN` to prevent unauthenticated
visitors from starting downloads or consuming the CPU worker. Find its value in
the service's environment settings after deployment; the app asks for it on
the first API request and keeps it for the current browser tab. Health checks
and the UI remain accessible without the key. After a server restart, completed
job history is recovered and any interrupted in-progress job is reported as
failed; media and finished clips remain on disk.

[Vercel's container functions](https://vercel.com/kb/guide/does-vercel-support-docker-deployments)
scale to zero and do not provide durable local filesystems, so they cannot
directly host this app's current disk-backed processing workflow. The
repository's existing root `vercel.json` belongs to the Network Blackout
Analyzer site and is not changed by this service setup. The persistent worker
deployment is configured separately through Render.

## Workflow

1. Select YouTube video or public live stream and retrieve metadata.
2. Select a maximum video quality and MP4/WebM/MKV or audio-only MP3/WAV.
3. Extract a video or record a live segment. Recording starts at current
   authorized access, has a requested duration limit, and can be stopped from
   the UI. Partial recordings are saved when yt-dlp leaves a finalized media
   file.
4. Transcribe the saved media using OpenAI Whisper. Word timestamps are grouped
   into sentences using punctuation and pause gaps.
5. Sentence embeddings rank potential educational, surprising, opinionated,
   Q&A, storytelling, and humorous moments. Review/edit start, end, and title.
6. Render selected moments in 9:16 using center crop, sampled face-centered
   smart crop, or a blurred background. Cuts can snap to nearby sentence
   boundaries. Burn in optional word-timed subtitles with editable styling and
   content-word highlighting.
7. Preview and download MP4 exports from the `clips/` folder.

## API outline

- `POST /api/metadata` with `{"url":"https://www.youtube.com/watch?v=..."}`.
- `POST /api/jobs/extract` with URL, quality, and output format.
- `POST /api/jobs/record` with the same fields and `live_duration_seconds`.
- `GET /api/jobs/{job_id}` to poll state/progress; `POST .../cancel` to cancel
  or stop recording.
- `POST /api/jobs/{job_id}/analyze` after extraction completes.
- `POST /api/jobs/{analysis_job_id}/clips` with editable clip intervals and
  export settings.

Jobs run in a bounded thread pool and report status, progress, and errors.
Downloads are cached in-process by URL/quality/output format to avoid repeating
identical work while the server is running.
Job records are stored in SQLite at `JOBS_DB_PATH`; for deployments, point this
to persistent storage. Configure `APP_ACCESS_TOKEN` to require a bearer access
key for all `/api/` routes.

## Validation and tests

```powershell
python -m pip check
python -m backend.utils.dependency_check
python -m pytest
python -m backend.utils.smoke_test
python -m backend.utils.smoke_test --with-whisper --model tiny
```

Tests use synthetic video/audio: URL validation, sentence grouping, semantic
scoring behavior, clip/filter bounds, FFmpeg metadata/conversion/audio
extraction, and an end-to-end vertical MP4 render with synchronized captions
and audio. The optional Whisper smoke command downloads/loads a real model and
runs CPU transcription on generated audio.

## Known limitations

- YouTube's availability, region, account, age, or live-stream restrictions are
  enforced by YouTube/yt-dlp; no bypass is provided.
- Live capture requires a currently accessible public broadcast. It cannot
  recover footage from before capture began. If stopping interrupts an
  unfinished yt-dlp fragment, the partial may not be finalizable.
- Smart crop estimates a stable face center from sampled frames; it is not
  frame-by-frame subject tracking.
- Moment quality depends on language, audio quality, Whisper model, and the
  downloaded semantic model. The user can edit every suggested interval/title.
- Local synthetic media is used for automated testing. No third-party video or
  live broadcast was downloaded for this verification.
- Local jobs run in a bounded thread pool. On a cloud instance, use one worker
  and persistent storage for the SQLite job database, downloads, clips, and AI
  model cache.

## Project layout

```text
backend/
  main.py                 FastAPI entry point and local UI serving
  config.py               Environment-backed configuration
  routes/                 Metadata, extraction, analysis, clip API
  services/               Background jobs and extraction orchestration
  extractors/             YouTube URL/metadata/format/download integration
  processors/             FFmpeg/OpenCV vertical renderer
  ai_engine/              OpenAI Whisper and semantic suggestions
  utils/                  FFmpeg and dependency checks
frontend/index.html       Working browser workflow
downloads/ clips/ temp/ logs/
tests/
requirements.txt
requirements-dev.txt
.env.example
```
