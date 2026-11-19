from pathlib import Path
import subprocess
import threading
import time

import numpy as np
import pytest

from backend.ai_engine import suggestions
from backend.ai_engine import transcription
from backend.ai_engine.transcription import _sentence_chunks
from backend.config import Settings
from backend.extractors import youtube
from backend.extractors.youtube import normalize_youtube_url
from backend.models import ClipSpec, GenerateRequest
from backend.processors import video
from backend.processors.video import _important_words, _snap_to_sentences, _video_filter
from backend.services.jobs import Job, JobManager
from backend.services import extraction


def test_youtube_url_normalizes_and_rejects_non_youtube_sources() -> None:
    assert normalize_youtube_url("https://youtu.be/Abcdef12345?t=20") == (
        "https://www.youtube.com/watch?v=Abcdef12345"
    )
    with pytest.raises(ValueError):
        normalize_youtube_url("https://youtube.com.attacker.example/watch?v=Abcdef12345")
    with pytest.raises(ValueError):
        normalize_youtube_url("http://www.youtube.com/watch?v=Abcdef12345")


def test_sentence_chunks_respect_pause_and_punctuation() -> None:
    words = [
        {"start": 0.0, "end": 0.2, "word": " That's"},
        {"start": 0.2, "end": 0.6, "word": " useful."},
        {"start": 1.8, "end": 2.0, "word": " Really"},
        {"start": 2.0, "end": 2.2, "word": "?"},
    ]

    sentences = _sentence_chunks(words, pause_seconds=0.8)

    assert [sentence["text"] for sentence in sentences] == ["That's useful.", "Really?"]
    assert (sentences[0]["start"], sentences[0]["end"]) == (0.0, 0.6)


def test_suggestions_rank_semantic_categories_and_limit_overlap(monkeypatch) -> None:
    class FakeModel:
        def encode(self, texts, **_kwargs):
            vectors = []
            for text in texts:
                vector = np.zeros(2, dtype=np.float32)
                vector[0 if "teaches" in text or "explanation" in text.lower() else 1] = 1
                vectors.append(vector)
            return np.asarray(vectors)

    monkeypatch.setattr(suggestions, "_model", lambda: FakeModel())
    transcript = {
        "segments": [
            {"start": 0, "end": 9, "text": "Here is an explanation that teaches the key concept."},
            {"start": 9, "end": 20, "text": "This additional detail makes the concept practical."},
            {"start": 20, "end": 31, "text": "A separate useful example and conclusion."},
        ]
    }

    candidates = suggestions.suggest_candidates(transcript, max_candidates=3)

    assert candidates
    assert candidates[0]["category"] == "educational explanation"
    assert 0 <= candidates[0]["confidence"] <= 1
    assert candidates[0]["end"] > candidates[0]["start"]


def test_clip_spec_and_vertical_filters_keep_valid_bounds() -> None:
    with pytest.raises(ValueError):
        ClipSpec(start=5, end=4, title="Backwards")
    with pytest.raises(ValueError):
        ClipSpec(start=0, end=181, title="Too long")

    video_filter, graph = _video_filter("center", 1080, 1920, 0.5)
    assert graph is None
    assert video_filter and "force_original_aspect_ratio=increase" in video_filter
    assert "crop=1080:1920" in video_filter

    blurred_filter, blurred_graph = _video_filter("blurred", 720, 1280, 0.5)
    assert blurred_filter is None
    assert blurred_graph and "boxblur" in blurred_graph and "overlay" in blurred_graph
    assert _snap_to_sentences(
        10.2,
        29.3,
        [{"start": 9.0, "end": 15.0}, {"start": 28.0, "end": 30.0}],
    ) == (9.0, 30.0)


def test_sentence_and_export_settings_are_strictly_typed() -> None:
    request = GenerateRequest(
        clips=[ClipSpec(start=0, end=15, title="A good moment")],
        subtitle_color="#ffcc00",
    )
    assert request.subtitle_color == "#ffcc00"
    settings = Settings(_env_file=None, ffmpeg_path=r"C:\media\ffmpeg.exe")
    assert settings.ffmpeg_path == r"C:\media\ffmpeg.exe"
    assert _important_words(
        [
            {"word": " useful"},
            {"word": " useful"},
            {"word": " useful"},
            {"word": " explanation."},
        ]
    ) == {"explanation"}


def test_downloader_selects_requested_quality_and_honors_cancel(monkeypatch) -> None:
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            captured["progress_hooks"][0]({"status": "finished"})
            return {
                "id": "Abcdef12345",
                "title": "Sample",
                "requested_downloads": [{"filepath": "sample.webm"}],
            }

        def prepare_filename(self, _info):
            return "sample.webm"

    monkeypatch.setattr(youtube, "YoutubeDL", FakeYoutubeDL)
    progress = []
    result = youtube.download_media(
        url="https://www.youtube.com/watch?v=Abcdef12345",
        destination="sample.%(ext)s",
        quality="720",
        output_format="webm",
        progress_hook=progress.append,
        cancel_event=threading.Event(),
    )

    assert "[height<=720][ext=webm]" in captured["format"]
    assert captured["merge_output_format"] == "webm"
    assert result["candidate_paths"] == ["sample.webm"]
    assert progress == [{"status": "finished"}]

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(youtube.DownloadError, match="cancelled by user"):
        youtube.download_media(
            url="https://www.youtube.com/watch?v=Abcdef12345",
            destination="sample.%(ext)s",
            quality="best",
            output_format="mp4",
            progress_hook=lambda _progress: None,
            cancel_event=cancelled,
        )


def test_job_status_serialization_excludes_thread_lock() -> None:
    status = JobManager._serialize(Job(id="job-1", type="extract"))

    assert status["id"] == "job-1"
    assert status["status"] == "queued"
    assert "_cancel" not in status


def test_background_job_exposes_result_and_progress() -> None:
    manager = JobManager()

    def worker(context):
        context.update(progress=45, stage="Working", message="Processing")
        return {"ok": True}

    try:
        submitted = manager.submit("test", worker)
        deadline = time.monotonic() + 5
        job = manager.get(submitted.id)
        while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            job = manager.get(submitted.id)

        assert job["status"] == "completed"
        assert job["progress"] == 100
        assert job["result"] == {"ok": True}
    finally:
        manager._executor.shutdown(wait=True)


def test_persistent_jobs_survive_restart_and_mark_running_jobs_interrupted(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    manager = JobManager(database_path=database_path)
    interrupted = Job(id="interrupted-job", type="analysis", status="running")
    manager._jobs[interrupted.id] = interrupted
    manager._persist(interrupted)

    def worker(_context):
        return {"source_path": "downloads/source.mp4", "candidates": []}

    try:
        submitted = manager.submit("analysis", worker)
        deadline = time.monotonic() + 5
        job = manager.get(submitted.id)
        while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            job = manager.get(submitted.id)
        assert job["status"] == "completed"
    finally:
        manager._executor.shutdown(wait=True)

    restarted = JobManager(database_path=database_path)
    try:
        restored = restarted.get(submitted.id)
        stopped = restarted.get("interrupted-job")
        assert restored["status"] == "completed"
        assert restored["result"]["source_path"] == "downloads/source.mp4"
        assert stopped["status"] == "failed"
        assert stopped["stage"] == "Interrupted"
    finally:
        restarted._executor.shutdown(wait=True)


def test_extraction_moves_result_and_reuses_identical_cached_download(
    tmp_path,
    monkeypatch,
) -> None:
    settings = Settings(
        _env_file=None,
        downloads_dir=tmp_path / "downloads",
        temp_dir=tmp_path / "temp",
    )
    monkeypatch.setattr(extraction, "get_settings", lambda: settings)
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs["url"])
        filepath = Path(kwargs["destination"].replace("%(id)s", "video-1").replace("%(ext)s", "mp4"))
        filepath.write_bytes(b"synthetic-video-data")
        kwargs["progress_hook"]({"status": "finished"})
        return {
            "id": "video-1",
            "title": "Authorized sample",
            "is_live": False,
            "candidate_paths": [str(filepath)],
        }

    monkeypatch.setattr(extraction, "download_media", fake_download)

    class Manager:
        def cancel_event(self, _job_id):
            return threading.Event()

    class Context:
        job_id = "extract-test"
        manager = Manager()
        cancelled = False

        def update(self, **_kwargs):
            return None

        def check_cancelled(self):
            return None

    args = {
        "url": "https://www.youtube.com/watch?v=Abcdef12345",
        "quality": "720",
        "output_format": "mp4",
        "context": Context(),
    }
    downloaded = extraction.extract_to_downloads(**args)
    cached = extraction.extract_to_downloads(**args)

    assert Path(downloaded["path"]).read_bytes() == b"synthetic-video-data"
    assert cached["reused"] is True
    assert len(calls) == 1
    assert list(settings.temp_dir.iterdir()) == []


@pytest.mark.parametrize("framing", ["center", "smart", "blurred"])
def test_synthetic_video_renders_vertical_mp4_with_synchronized_captions(
    tmp_path,
    monkeypatch,
    framing,
) -> None:
    settings = Settings(
        _env_file=None,
        clips_dir=tmp_path / "clips",
        temp_dir=tmp_path / "temp",
    )
    monkeypatch.setattr(video, "get_settings", lambda: settings)
    monkeypatch.setattr("backend.utils.toolchain.get_settings", lambda: settings)
    source = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "4",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
        timeout=30,
    )

    class Context:
        job_id = "test-render"
        cancelled = False

        def check_cancelled(self):
            return None

        def update(self, **_kwargs):
            return None

    outputs = video.render_clips(
        source=source,
        specs=[ClipSpec(start=0.5, end=3.0, title="Synthetic clip")],
        transcript={
            "words": [
                {"start": 0.7, "end": 1.0, "word": "Hello"},
                {"start": 1.0, "end": 1.4, "word": " world."},
            ]
        },
        request=GenerateRequest(
            clips=[ClipSpec(start=0.5, end=3.0, title="Synthetic clip")],
            resolution="720x1280",
            subtitles=True,
            framing=framing,
        ),
        source_title="Synthetic source",
        context=Context(),
    )

    assert len(outputs) == 1
    result = video.probe(tmp_path / "clips" / outputs[0]["filename"])
    streams = result["streams"]
    assert any(stream["codec_type"] == "video" and stream["width"] == 720 and stream["height"] == 1280 for stream in streams)
    assert any(stream["codec_type"] == "audio" for stream in streams)
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert abs(float(video_stream["duration"]) - float(audio_stream["duration"])) < 0.1
    assert 2.4 <= result["duration"] <= 2.7


def test_transcription_chunks_long_audio_and_offsets_word_timestamps(
    tmp_path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, temp_dir=tmp_path / "temp")
    monkeypatch.setattr(transcription, "get_settings", lambda: settings)
    monkeypatch.setattr(video, "probe", lambda _path: {"duration": 61.0})
    source = tmp_path / "long.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "61",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(source),
        ],
        check=True,
        timeout=30,
    )

    class Model:
        def transcribe(self, _path, **_kwargs):
            return {
                "language": "en",
                "segments": [
                    {
                        "start": 0.1,
                        "end": 0.5,
                        "text": "hello world.",
                        "words": [
                            {"start": 0.1, "end": 0.25, "word": " hello", "probability": 0.9},
                            {"start": 0.25, "end": 0.5, "word": " world.", "probability": 0.9},
                        ],
                    }
                ],
            }

    monkeypatch.setattr(transcription, "_load_model", lambda *_args: Model())
    result = transcription.transcribe(source, model_name="tiny")

    assert len(result["words"]) == 4
    assert result["words"][0]["start"] == 0.1
    assert result["words"][2]["start"] == 60.1
    assert result["segments"][1]["text"] == "hello world."
    assert result["duration"] == 61
