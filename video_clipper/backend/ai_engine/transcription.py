import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from backend.config import get_settings
from backend.utils.toolchain import resolve_executable

_AUDIO_CHUNK_SECONDS = 60
_MODEL_LOCK = threading.RLock()
_WHISPER_MODEL: Any = None
_WHISPER_MODEL_KEY: tuple[str, str] | None = None


def _load_model(model_name: str, cache_dir: str) -> Any:
    global _WHISPER_MODEL, _WHISPER_MODEL_KEY

    cache_key = (model_name, cache_dir)
    with _MODEL_LOCK:
        if _WHISPER_MODEL is not None and _WHISPER_MODEL_KEY == cache_key:
            return _WHISPER_MODEL
        import whisper

        _WHISPER_MODEL = whisper.load_model(
            model_name,
            device="cpu",
            download_root=cache_dir,
        )
        _WHISPER_MODEL_KEY = cache_key
        return _WHISPER_MODEL


def _sentence_chunks(words: list[dict[str, Any]], pause_seconds: float) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        if current and (
            word["start"] - current[-1]["end"] >= pause_seconds
            or current[-1]["word"].rstrip().endswith((".", "!", "?", "。"))
        ):
            chunks.append(_make_sentence(current))
            current = []
        current.append(word)
    if current:
        chunks.append(_make_sentence(current))
    return chunks


def _make_sentence(words: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start": round(words[0]["start"], 3),
        "end": round(words[-1]["end"], 3),
        "text": "".join(word["word"] for word in words).strip(),
        "words": words,
        "pause_after": 0.0,
    }


def transcribe(
    media_path: Path,
    model_name: str | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    if not media_path.is_file():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    settings = get_settings()
    model_name = model_name or settings.whisper_model
    logger.info("Loading OpenAI Whisper model {}", model_name)
    model = _load_model(model_name, str(settings.model_cache_dir.resolve()))
    from backend.processors.video import probe

    media_duration = probe(media_path)["duration"]
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_executable("ffmpeg", settings.ffmpeg_path)
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    languages: list[str] = []

    with tempfile.TemporaryDirectory(
        prefix="transcription-",
        dir=settings.temp_dir.resolve(),
    ) as directory:
        pattern = str(Path(directory) / "audio-%05d.wav")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(media_path),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-f",
                "segment",
                "-segment_time",
                str(_AUDIO_CHUNK_SECONDS),
                "-reset_timestamps",
                "1",
                pattern,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        chunks = sorted(Path(directory).glob("audio-*.wav"))
        if not chunks:
            raise RuntimeError("FFmpeg did not extract any audio chunks for transcription")
        chunk_count = len(chunks)
        for chunk_index, chunk_path in enumerate(chunks):
            if progress:
                progress(
                    5 + chunk_index / chunk_count * 90,
                    f"Transcribing audio chunk {chunk_index + 1} of {chunk_count}",
                )
            offset = chunk_index * _AUDIO_CHUNK_SECONDS
            with _MODEL_LOCK:
                result = model.transcribe(
                    str(chunk_path),
                    word_timestamps=True,
                    fp16=False,
                    verbose=False,
                )
            language = result.get("language")
            if language:
                languages.append(language)
            for item in result.get("segments", []):
                word_items = []
                for word in item.get("words", []):
                    entry = {
                        "start": round(float(word["start"]) + offset, 3),
                        "end": round(float(word["end"]) + offset, 3),
                        "word": word["word"],
                        "probability": round(float(word.get("probability", 0)), 4),
                    }
                    word_items.append(entry)
                    words.append(entry)
                if not word_items and item["text"].strip():
                    word_items = [
                        {
                            "start": round(float(item["start"]) + offset, 3),
                            "end": round(float(item["end"]) + offset, 3),
                            "word": item["text"].strip(),
                            "probability": 0.0,
                        }
                    ]
                    words.extend(word_items)
                if word_items:
                    segments.extend(_sentence_chunks(word_items, pause_seconds=0.8))

    for index in range(len(segments) - 1):
        segments[index]["pause_after"] = round(
            max(0, segments[index + 1]["start"] - segments[index]["end"]),
            3,
        )
    if progress:
        progress(100, "Transcription complete")

    return {
        "language": max(set(languages), key=languages.count) if languages else None,
        "language_probability": None,
        "duration": round(float(media_duration), 3),
        "segments": segments,
        "words": words,
        "model": model_name,
    }
