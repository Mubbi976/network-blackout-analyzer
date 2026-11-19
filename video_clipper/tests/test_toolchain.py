import pytest

from backend.utils.toolchain import resolve_executable


def test_resolve_executable_rejects_missing_configured_path(tmp_path) -> None:
    missing = tmp_path / "missing-ffmpeg.exe"

    with pytest.raises(FileNotFoundError, match="Configured ffmpeg executable not found"):
        resolve_executable("ffmpeg", str(missing))
