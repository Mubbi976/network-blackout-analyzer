from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "Video Clipper"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    downloads_dir: Path = Path("downloads")
    clips_dir: Path = Path("clips")
    temp_dir: Path = Path("temp")
    logs_dir: Path = Path("logs")
    model_cache_dir: Path = Path("models")
    jobs_db_path: Path = _PROJECT_ROOT / "temp" / "jobs.sqlite3"
    app_access_token: str | None = None
    whisper_model: str = "small"
    semantic_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_workers: int = Field(default=2, ge=1, le=8)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
