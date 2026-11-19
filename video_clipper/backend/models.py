from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


Quality = Literal["best", "1080", "720", "480"]
OutputFormat = Literal["mp4", "webm", "mkv", "mp3", "wav"]
FramingMode = Literal["center", "smart", "blurred"]
SubtitleStyle = Literal["minimal", "professional", "bold"]
WhisperModelName = Literal[
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large",
    "turbo",
]


class YouTubeRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        from backend.extractors.youtube import normalize_youtube_url

        return normalize_youtube_url(value)


class ExtractionRequest(YouTubeRequest):
    quality: Quality = "best"
    output_format: OutputFormat = "mp4"
    live_duration_seconds: int | None = Field(default=None, ge=10, le=86_400)

    @model_validator(mode="after")
    def validate_live_duration(self) -> "ExtractionRequest":
        if self.live_duration_seconds is not None and self.output_format in {"mp3", "wav"}:
            raise ValueError("Live recordings must be saved as a video format")
        return self


class AnalyzeRequest(BaseModel):
    model: WhisperModelName | None = None
    max_candidates: int = Field(default=8, ge=1, le=20)


class ClipSpec(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_interval(self) -> "ClipSpec":
        if self.end <= self.start:
            raise ValueError("Clip end must be after its start")
        if self.end - self.start > 180:
            raise ValueError("Clip duration cannot exceed 180 seconds")
        return self


class GenerateRequest(BaseModel):
    clips: list[ClipSpec] = Field(min_length=1, max_length=20)
    framing: FramingMode = "center"
    resolution: Literal["1080x1920", "720x1280"] = "1080x1920"
    preset: Literal["instagram", "youtube_shorts"] = "instagram"
    snap_to_sentences: bool = True
    subtitles: bool = True
    highlight_keywords: bool = True
    subtitle_style: SubtitleStyle = "professional"
    subtitle_font_size: int = Field(default=52, ge=18, le=96)
    subtitle_color: str = Field(default="white", pattern=r"^(?:[a-zA-Z]+|#[0-9a-fA-F]{6})$")
    subtitle_position: Literal["top", "middle", "bottom"] = "bottom"

    @field_validator("subtitle_color")
    @classmethod
    def validate_subtitle_color(cls, value: str) -> str:
        if value.startswith("#") or value.lower() in {"white", "yellow", "cyan", "lime"}:
            return value
        raise ValueError("Subtitle color must be white, yellow, cyan, lime, or #RRGGBB")
