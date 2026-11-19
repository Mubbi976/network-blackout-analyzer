import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger
from yt_dlp.utils import DownloadError

from backend.config import get_settings
from backend.extractors.youtube import download_media
from backend.services.jobs import JobContext

_MEDIA_EXTENSIONS = {"mp4", "webm", "mkv", "mp3", "wav", "m4a", "ts"}
_download_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _safe_stem(value: str, max_length: int = 72) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (stem or "video")[:max_length]


def _find_media_files(folder: Path) -> list[Path]:
    return [
        path
        for path in folder.iterdir()
        if _is_media_file(path)
    ]


def _is_media_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower().lstrip(".") in _MEDIA_EXTENSIONS
        and not path.name.endswith((".part", ".ytdl"))
    )


def extract_to_downloads(
    *,
    url: str,
    quality: str,
    output_format: str,
    context: JobContext,
    live_duration_seconds: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    cache_key = (url, quality, output_format)
    if live_duration_seconds is None:
        with _cache_lock:
            cached = _download_cache.get(cache_key)
            if cached and Path(cached["path"]).is_file():
                return {**cached, "reused": True}
    workdir = settings.temp_dir.resolve() / f"extract-{context.job_id}"
    workdir.mkdir(parents=True, exist_ok=False)
    template = str(workdir / "%(id)s.%(ext)s")
    start = time.monotonic()
    last_progress = 0.0
    result: dict[str, Any] | None = None
    download_error: DownloadError | None = None

    def report(progress: dict[str, Any]) -> None:
        nonlocal last_progress
        status = progress.get("status")
        if status == "downloading":
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
            downloaded = progress.get("downloaded_bytes") or 0
            percent = (downloaded / total * 90) if total else last_progress
            last_progress = max(last_progress, percent)
            speed = progress.get("speed")
            suffix = f" at {speed / 1_000_000:.1f} MB/s" if speed else ""
            context.update(
                progress=percent,
                stage="Recording live stream" if live_duration_seconds else "Downloading",
                message=f"{downloaded / 1_000_000:.1f} MB downloaded{suffix}",
            )
        elif status == "finished":
            context.update(progress=92, stage="Finalizing", message="Finalizing downloaded media")

    try:
        context.update(progress=0, stage="Connecting", message="Connecting to YouTube")
        try:
            result = download_media(
                url=url,
                destination=template,
                quality=quality,
                output_format=output_format,
                progress_hook=report,
                cancel_event=context.manager.cancel_event(context.job_id),
                live_duration_seconds=live_duration_seconds,
            )
        except DownloadError as error:
            download_error = error

        files = _find_media_files(workdir)
        candidate_paths = [
            Path(path)
            for path in (result or {}).get("candidate_paths", [])
            if _is_media_file(Path(path))
        ]
        files = list(dict.fromkeys(candidate_paths + files))

        if context.cancelled and live_duration_seconds and files:
            download_error = DownloadError("Live recording stopped by user")
        else:
            context.check_cancelled()
        if download_error and not (live_duration_seconds and files):
            raise download_error
        if not files:
            if download_error:
                raise download_error
            raise RuntimeError("The downloader completed without producing a media file")

        media_file = max(files, key=lambda path: path.stat().st_size)
        title = (result or {}).get("title") or "live-recording"
        video_id = (result or {}).get("id") or context.job_id[:8]
        base_name = f"{_safe_stem(title)}-{_safe_stem(video_id, 24)}"
        destination = settings.downloads_dir.resolve() / f"{base_name}{media_file.suffix.lower()}"
        duplicate_number = 1
        while destination.exists():
            destination = (
                settings.downloads_dir.resolve()
                / f"{base_name}-{duplicate_number}{media_file.suffix.lower()}"
            )
            duplicate_number += 1

        context.update(progress=96, stage="Saving", message="Saving media to downloads")
        shutil.move(str(media_file), str(destination))
        is_partial = download_error is not None
        logger.info("Saved media for job {} at {}", context.job_id, destination)
        saved = {
            "path": str(destination),
            "filename": destination.name,
            "title": title,
            "video_id": video_id,
            "is_live": live_duration_seconds is not None,
            "partial": is_partial,
            "recording_seconds": round(time.monotonic() - start, 1)
            if live_duration_seconds
            else None,
        }
        if live_duration_seconds is None:
            with _cache_lock:
                _download_cache[cache_key] = saved
        return saved
    finally:
        if workdir.exists():
            shutil.rmtree(workdir)
