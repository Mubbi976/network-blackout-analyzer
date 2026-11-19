import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.config import get_settings
from backend.utils.toolchain import resolve_executable


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local FFmpeg media smoke tests.")
    parser.add_argument(
        "--with-whisper",
        action="store_true",
        help="Download/load the OpenAI Whisper tiny model and run CPU transcription.",
    )
    parser.add_argument("--model", default="tiny", help="Whisper model name (default: tiny)")
    args = parser.parse_args()

    settings = get_settings()
    try:
        ffmpeg = resolve_executable("ffmpeg", settings.ffmpeg_path)
        ffprobe = resolve_executable("ffprobe", settings.ffprobe_path)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="video-clipper-smoke-") as directory:
        root = Path(directory)
        source = root / "synthetic.mp4"
        converted = root / "converted.mp4"
        audio = root / "audio.wav"

        run(
            [
                ffmpeg,
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
                "2",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-shortest",
                str(source),
            ]
        )
        metadata = json.loads(
            run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of",
                    "json",
                    str(source),
                ]
            ).stdout
        )
        duration = float(metadata["format"]["duration"])
        if duration <= 0 or not any(
            stream.get("codec_type") == "video" for stream in metadata["streams"]
        ):
            raise RuntimeError("FFprobe did not report a valid video and duration")
        print(f"OK      metadata extraction ({duration:.2f}s)")

        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-t",
                "1",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                str(converted),
            ]
        )
        if not converted.is_file() or converted.stat().st_size == 0:
            raise RuntimeError("FFmpeg conversion did not create an output video")
        print("OK      video conversion")

        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "pcm_s16le",
                str(audio),
            ]
        )
        if not audio.is_file() or audio.stat().st_size == 0:
            raise RuntimeError("FFmpeg audio extraction did not create a WAV file")
        print("OK      audio extraction")

        if args.with_whisper:
            import whisper

            model = whisper.load_model(
                args.model,
                device="cpu",
                download_root=str(settings.model_cache_dir),
            )
            result = model.transcribe(str(audio), fp16=False, word_timestamps=True, verbose=False)
            print(
                f"OK      OpenAI Whisper transcription runtime "
                f"(model={args.model}, detected_language={result['language']})"
            )
        else:
            print("SKIP    Whisper inference (rerun with --with-whisper)")

    print("OK      temporary media cleaned up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
