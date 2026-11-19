import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from backend.config import get_settings

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_VIDEO_EXTENSIONS = {"mp4", "webm", "mkv"}
_AUDIO_EXTENSIONS = {"mp3", "wav"}


def normalize_youtube_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in _YOUTUBE_HOSTS:
        raise ValueError("Use an HTTPS YouTube video or public live-stream URL")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Credentials and custom ports are not allowed in YouTube URLs")

    video_id: str | None = None
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] in {"live", "shorts", "embed", "v"}:
            video_id = parts[1]

    if video_id is None or not _VIDEO_ID.fullmatch(video_id):
        raise ValueError("URL must identify a YouTube video or live stream")
    return f"https://www.youtube.com/watch?v={video_id}"


def _base_options() -> dict[str, Any]:
    settings = get_settings()
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "extractor_retries": 3,
        "retries": 5,
    }
    if settings.ffmpeg_path:
        options["ffmpeg_location"] = settings.ffmpeg_path
    return options


def _format_options(info: dict[str, Any]) -> list[dict[str, Any]]:
    formats = []
    for item in info.get("formats", []):
        ext = item.get("ext")
        if ext not in _VIDEO_EXTENSIONS | {"m4a", "mp3", "wav", "opus"}:
            continue
        if not item.get("url"):
            continue
        formats.append(
            {
                "format_id": str(item.get("format_id", "")),
                "ext": ext,
                "height": item.get("height"),
                "width": item.get("width"),
                "filesize": item.get("filesize") or item.get("filesize_approx"),
                "note": item.get("format_note"),
                "video_codec": item.get("vcodec"),
                "audio_codec": item.get("acodec"),
            }
        )
    return formats


def get_metadata(url: str) -> dict[str, Any]:
    normalized = normalize_youtube_url(url)
    with YoutubeDL(_base_options()) as ydl:
        info = ydl.extract_info(normalized, download=False)
    if info is None:
        raise DownloadError("YouTube returned no metadata for this URL")
    return {
        "id": info.get("id"),
        "url": normalized,
        "title": info.get("title") or "Untitled video",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url"),
        "is_live": bool(info.get("is_live") or info.get("was_live")),
        "formats": _format_options(info),
    }


def download_media(
    url: str,
    destination: str,
    quality: str,
    output_format: str,
    progress_hook: Any,
    cancel_event: Any,
    live_duration_seconds: int | None = None,
) -> dict[str, Any]:
    import time

    normalized = normalize_youtube_url(url)
    audio_only = output_format in _AUDIO_EXTENSIONS
    if audio_only:
        format_selector = "bestaudio/best"
    elif output_format == "mp4":
        height_filter = "" if quality == "best" else f"[height<={quality}]"
        format_selector = (
            f"bestvideo{height_filter}[ext=mp4]+bestaudio[ext=m4a]/"
            f"best{height_filter}[ext=mp4]"
        )
    elif output_format == "webm":
        height_filter = "" if quality == "best" else f"[height<={quality}]"
        format_selector = (
            f"bestvideo{height_filter}[ext=webm]+bestaudio[ext=webm]/"
            f"best{height_filter}[ext=webm]"
        )
    else:
        height_filter = "" if quality == "best" else f"[height<={quality}]"
        format_selector = f"bestvideo{height_filter}+bestaudio/best{height_filter}"

    start_time = time.monotonic()

    def checked_hook(progress: dict[str, Any]) -> None:
        if cancel_event.is_set():
            raise DownloadError("Download cancelled by user")
        if live_duration_seconds and time.monotonic() - start_time >= live_duration_seconds:
            raise DownloadError("Requested live recording duration reached")
        progress_hook(progress)

    options = _base_options()
    options.update(
        {
            "format": format_selector,
            "outtmpl": destination,
            "noplaylist": True,
            "continuedl": True,
            "fragment_retries": 6,
            "file_access_retries": 3,
            "progress_hooks": [checked_hook],
            "merge_output_format": output_format if not audio_only else None,
            "postprocessors": (
                [{"key": "FFmpegExtractAudio", "preferredcodec": output_format}]
                if audio_only
                else []
            ),
            "hls_use_mpegts": bool(live_duration_seconds is not None),
        }
    )
    if live_duration_seconds:
        options["live_from_start"] = False

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(normalized, download=True)
        if cancel_event.is_set():
            raise DownloadError("Download cancelled by user")

        requested = info.get("requested_downloads") or []
        candidates = [
            item.get("filepath") or item.get("_filename")
            for item in requested
            if item.get("filepath") or item.get("_filename")
        ]
        candidates.extend(
            [
                info.get("filepath"),
                ydl.prepare_filename(info),
            ]
        )
        return {
            "id": info.get("id"),
            "title": info.get("title") or "video",
            "is_live": bool(info.get("is_live") or info.get("was_live")),
            "candidate_paths": list(dict.fromkeys(path for path in candidates if path)),
        }
