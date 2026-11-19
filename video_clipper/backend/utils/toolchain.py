import shutil
import subprocess
from pathlib import Path

from backend.config import get_settings


def resolve_executable(name: str, configured_path: str | None) -> str:
    if configured_path:
        executable = Path(configured_path).expanduser()
        if not executable.is_file():
            raise FileNotFoundError(f"Configured {name} executable not found: {executable}")
        return str(executable.resolve())

    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(
            f"{name} was not found on PATH; install FFmpeg or configure its executable path in .env"
        )
    return executable


def tool_version(name: str) -> str:
    settings = get_settings()
    configured_path = {
        "ffmpeg": settings.ffmpeg_path,
        "ffprobe": settings.ffprobe_path,
    }.get(name)
    executable = resolve_executable(name, configured_path)
    result = subprocess.run(
        [executable, "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    first_line = result.stdout.splitlines()
    if not first_line:
        raise RuntimeError(f"{name} returned no version information")
    return first_line[0]
