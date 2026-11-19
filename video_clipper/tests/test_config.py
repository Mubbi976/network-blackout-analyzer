from pathlib import Path

from backend.config import Settings


def test_settings_can_be_configured_without_a_dotenv_file() -> None:
    settings = Settings(
        _env_file=None,
        app_name="Test Clip App",
        ffmpeg_path=r"C:\ffmpeg\bin\ffmpeg.exe",
        downloads_dir=Path("test-downloads"),
    )

    assert settings.app_name == "Test Clip App"
    assert settings.ffmpeg_path == r"C:\ffmpeg\bin\ffmpeg.exe"
    assert settings.downloads_dir == Path("test-downloads")
