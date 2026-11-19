import html
import json
import re
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
from loguru import logger

from backend.config import get_settings
from backend.models import ClipSpec, GenerateRequest
from backend.services.jobs import JobContext
from backend.utils.toolchain import resolve_executable

_COLOR_MAP = {
    "white": "00FFFFFF",
    "yellow": "0000FFFF",
    "cyan": "00FFFF00",
    "lime": "0000FF00",
}


def probe(path: Path) -> dict[str, Any]:
    settings = get_settings()
    executable = resolve_executable("ffprobe", settings.ffprobe_path)
    result = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    info = json.loads(result.stdout)
    info["duration"] = float(info.get("format", {}).get("duration") or 0)
    return info


def _smart_crop_center(path: Path, duration: float) -> float:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open source video: {path.name}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = min(duration, frame_count / fps if frame_count else duration)
    cascade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    positions = []
    try:
        for timestamp in [i * duration / 19 for i in range(20)]:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.15,
                minNeighbors=4,
                minSize=(24, 24),
            )
            if len(faces):
                largest = max(faces, key=lambda face: face[2] * face[3])
                positions.append((largest[0] + largest[2] / 2) / frame.shape[1])
    finally:
        capture.release()
    if not positions:
        logger.info("No face found in {}; using centered smart crop", path.name)
        return 0.5
    return max(0.1, min(0.9, sum(positions) / len(positions)))


def _video_filter(
    framing: str,
    width: int,
    height: int,
    crop_center: float,
) -> tuple[str | None, str | None]:
    if framing == "blurred":
        graph = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=24:12[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
        return None, graph
    x_expr = "(iw-ow)*0.5" if framing == "center" else f"(iw-ow)*{crop_center:.5f}"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:x={x_expr}:y=(ih-oh)*0.5,setsar=1",
        None,
    )


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02},{millis:03}"


def _write_srt(
    path: Path,
    words: list[dict[str, Any]],
    start: float,
    end: float,
    important_words: set[str] | None = None,
) -> None:
    selected = [
        word
        for word in words
        if word["end"] > start and word["start"] < end and word["word"].strip()
    ]
    cues = []
    for offset in range(0, len(selected), 5):
        group = selected[offset : offset + 5]
        cue_start = max(start, float(group[0]["start"])) - start
        cue_end = min(end, float(group[-1]["end"])) - start
        if cue_end <= cue_start:
            continue
        cue_text = []
        for item in group:
            word = item["word"]
            token = re.sub(r"[^a-zA-Z0-9'-]", "", word).lower()
            escaped_word = html.escape(word)
            if important_words and token in important_words:
                escaped_word = f'<font color="#FFD54A"><b>{escaped_word}</b></font>'
            cue_text.append(escaped_word)
        cues.append(
            f"{len(cues) + 1}\n{_srt_timestamp(cue_start)} --> {_srt_timestamp(cue_end)}\n"
            f"{''.join(cue_text).strip()}\n"
        )
    path.write_text("\n".join(cues), encoding="utf-8")


def _subtitle_filter(path: Path, request: GenerateRequest) -> str:
    filename = str(path.resolve()).replace("\\", "/")
    filename = filename.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")
    alignment = {"bottom": 2, "middle": 5, "top": 8}[request.subtitle_position]
    margin = 96 if request.subtitle_position == "bottom" else 60
    outline = {"minimal": 1, "professional": 2, "bold": 4}[request.subtitle_style]
    primary = _COLOR_MAP.get(request.subtitle_color.lower())
    if not primary:
        match = re.fullmatch(r"#([0-9a-fA-F]{6})", request.subtitle_color)
        if not match:
            raise ValueError("Subtitle color must be a named supported color or #RRGGBB")
        red, green, blue = match.group(1)[0:2], match.group(1)[2:4], match.group(1)[4:6]
        primary = f"00{blue}{green}{red}".upper()
    style = (
        f"FontName=Arial,FontSize={request.subtitle_font_size},PrimaryColour=&H{primary}&,"
        f"OutlineColour=&H80000000&,BorderStyle=1,Outline={outline},"
        f"Shadow=0,Alignment={alignment},MarginV={margin}"
    )
    return f"subtitles=filename='{filename}':force_style='{style}'"


def _snap_to_sentences(
    start: float,
    end: float,
    segments: list[dict[str, Any]],
    max_distance: float = 1.5,
) -> tuple[float, float]:
    starts = [float(segment["start"]) for segment in segments]
    ends = [float(segment["end"]) for segment in segments]
    nearby_start = [value for value in starts if abs(value - start) <= max_distance]
    nearby_end = [value for value in ends if abs(value - end) <= max_distance]
    snapped_start = min(nearby_start, key=lambda value: abs(value - start)) if nearby_start else start
    snapped_end = min(nearby_end, key=lambda value: abs(value - end)) if nearby_end else end
    return snapped_start, snapped_end


def _important_words(words: list[dict[str, Any]]) -> set[str]:
    stop_words = {
        "about", "after", "again", "also", "and", "because", "been", "before",
        "being", "but", "could", "does", "during", "from", "have", "into",
        "just", "more", "most", "only", "other", "over", "same", "some",
        "such", "than", "that", "their", "there", "these", "they", "this",
        "those", "through", "under", "very", "want", "were", "what", "when",
        "where", "which", "while", "with", "would", "your",
    }
    tokens = [
        re.sub(r"[^a-zA-Z0-9'-]", "", item["word"]).lower()
        for item in words
    ]
    counts = Counter(token for token in tokens if token)
    return {
        token
        for token in tokens
        if len(token) >= 5
        and token not in stop_words
        and counts[token] <= 2
    }


def render_clips(
    source: Path,
    specs: list[ClipSpec],
    transcript: dict[str, Any],
    request: GenerateRequest,
    source_title: str,
    context: JobContext,
) -> list[dict[str, Any]]:
    if not source.is_file():
        raise FileNotFoundError(f"Source media file not found: {source}")
    details = probe(source)
    if not any(item.get("codec_type") == "video" for item in details.get("streams", [])):
        raise ValueError("The selected source contains no video stream")
    duration = details["duration"]
    settings = get_settings()
    settings.clips_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_executable("ffmpeg", settings.ffmpeg_path)
    width, height = (1080, 1920) if request.resolution == "1080x1920" else (720, 1280)
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", source_title).strip("-.")[:64] or "clip"
    outputs = []

    for index, spec in enumerate(specs, start=1):
        context.check_cancelled()
        start, end = spec.start, spec.end
        if request.snap_to_sentences and transcript.get("segments"):
            snapped_start, snapped_end = _snap_to_sentences(
                start,
                end,
                transcript["segments"],
            )
            if snapped_end > snapped_start and snapped_end - snapped_start <= 180:
                start, end = snapped_start, snapped_end
        if end > duration:
            raise ValueError(f"Clip {index} ends after source duration ({duration:.2f}s)")
        if request.preset == "youtube_shorts" and end - start > 180:
            raise ValueError("YouTube Shorts exports must be 180 seconds or shorter")

        out_path = (
            settings.clips_dir.resolve()
            / f"{safe_title}-clip-{index:02d}-{context.job_id[:8]}.mp4"
        )
        subtitle_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="clipper-render-") as workdir:
            if request.subtitles and transcript.get("words"):
                subtitle_path = Path(workdir) / "captions.srt"
                important = (
                    _important_words(transcript["words"])
                    if request.highlight_keywords
                    else None
                )
                _write_srt(
                    subtitle_path,
                    transcript["words"],
                    start,
                    end,
                    important_words=important,
                )

            crop_center = (
                _smart_crop_center(source, duration)
                if request.framing == "smart"
                else 0.5
            )
            video_filter, filter_complex = _video_filter(
                request.framing,
                width,
                height,
                crop_center,
            )
            if subtitle_path:
                caption_filter = _subtitle_filter(subtitle_path, request)
                if video_filter:
                    video_filter = f"{video_filter},{caption_filter}"
                elif filter_complex:
                    filter_complex = filter_complex.replace(
                        ",setsar=1[v]",
                        f",setsar=1[base];[base]{caption_filter}[v]",
                    )
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
            ]
            if filter_complex:
                command.extend(["-filter_complex", filter_complex, "-map", "[v]"])
            elif video_filter:
                command.extend(["-vf", video_filter, "-map", "0:v:0"])
            command.extend(
                [
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "21",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    "-shortest",
                    str(out_path),
                ]
            )
            context.update(
                progress=(index - 1) / len(specs) * 100,
                stage="Rendering clips",
                message=f"Rendering clip {index} of {len(specs)}",
            )
            logger.info("Rendering clip {} for job {}", index, context.job_id)
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_file,
                )
                while process.poll() is None:
                    if context.cancelled:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        out_path.unlink(missing_ok=True)
                        raise RuntimeError("Rendering cancelled")
                    time.sleep(0.2)
                if process.returncode:
                    stderr_file.seek(0)
                    detail = stderr_file.read().decode("utf-8", errors="replace")[-2000:]
                    out_path.unlink(missing_ok=True)
                    raise RuntimeError(f"FFmpeg clip render failed: {detail}")

        try:
            rendered = probe(out_path)
            rendered_duration = rendered["duration"]
            if not out_path.is_file() or rendered_duration <= 0:
                raise RuntimeError(f"Rendered clip {index} failed metadata verification")
        except Exception:
            out_path.unlink(missing_ok=True)
            raise
        outputs.append(
            {
                "filename": out_path.name,
                "path": str(out_path),
                "duration": round(rendered_duration, 3),
                "width": width,
                "height": height,
                "title": spec.title,
                "start": round(start, 3),
                "end": round(end, 3),
            }
        )
    return outputs
