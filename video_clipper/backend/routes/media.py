from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from backend.ai_engine.suggestions import suggest_candidates
from backend.ai_engine.transcription import transcribe
from backend.config import get_settings
from backend.extractors.youtube import get_metadata
from backend.models import AnalyzeRequest, ExtractionRequest, GenerateRequest, YouTubeRequest
from backend.processors.video import render_clips
from backend.services.extraction import extract_to_downloads
from backend.services.jobs import JobContext, job_manager

router = APIRouter(prefix="/api", tags=["media"])


def _job_or_404(job_id: str) -> dict[str, Any]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/metadata")
def metadata(request: YouTubeRequest) -> dict[str, Any]:
    try:
        return get_metadata(request.url)
    except Exception as error:
        logger.warning("Metadata lookup failed: {}", error)
        raise HTTPException(status_code=502, detail=f"Could not retrieve YouTube metadata: {error}") from error


@router.get("/formats")
def formats(url: str = Query(min_length=10, max_length=2048)) -> list[dict[str, Any]]:
    try:
        return get_metadata(url)["formats"]
    except Exception as error:
        logger.warning("Format lookup failed: {}", error)
        raise HTTPException(status_code=502, detail=f"Could not retrieve formats: {error}") from error


def _submit_extraction(request: ExtractionRequest, live_seconds: int | None):
    try:
        job = job_manager.submit(
            "recording" if live_seconds is not None else "extraction",
            lambda context: extract_to_downloads(
                url=request.url,
                quality=request.quality,
                output_format=request.output_format,
                context=context,
                live_duration_seconds=live_seconds,
            ),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    return job_manager.get(job.id)


@router.post("/jobs/extract", status_code=202)
def start_extraction(request: ExtractionRequest) -> dict[str, Any]:
    if request.live_duration_seconds is not None:
        raise HTTPException(
            status_code=422,
            detail="Use /api/jobs/record for a time-limited live recording",
        )
    return _submit_extraction(request, None)


@router.post("/jobs/record", status_code=202)
def start_recording(request: ExtractionRequest) -> dict[str, Any]:
    if request.live_duration_seconds is None:
        raise HTTPException(status_code=422, detail="live_duration_seconds is required")
    return _submit_extraction(request, request.live_duration_seconds)


@router.get("/jobs")
def list_jobs() -> list[dict[str, Any]]:
    return job_manager.list()


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return _job_or_404(job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, str]:
    _job_or_404(job_id)
    if not job_manager.cancel(job_id):
        raise HTTPException(status_code=409, detail="Job is no longer active")
    return {"status": "cancellation requested"}


@router.post("/jobs/{job_id}/analyze", status_code=202)
def analyze_job(job_id: str, request: AnalyzeRequest) -> dict[str, Any]:
    source_job = _job_or_404(job_id)
    if source_job["status"] != "completed" or not source_job.get("result"):
        raise HTTPException(status_code=409, detail="Extraction must finish before analysis")
    media_path = Path(source_job["result"]["path"])
    if not media_path.is_file():
        raise HTTPException(status_code=410, detail="Extracted media is no longer available")

    def worker(context: JobContext) -> dict[str, Any]:
        context.update(progress=1, stage="Loading model", message="Preparing local Whisper model")

        def report_transcription_progress(value: float, message: str) -> None:
            context.check_cancelled()
            context.update(
                progress=value,
                stage="Transcribing",
                message=message,
            )

        transcription = transcribe(
            media_path,
            model_name=request.model,
            progress=report_transcription_progress,
        )
        context.check_cancelled()
        context.update(progress=60, stage="Finding moments", message="Scoring transcript moments")
        candidates = suggest_candidates(
            transcription,
            max_candidates=request.max_candidates,
        )
        return {
            "source_path": str(media_path.resolve()),
            "source_title": source_job["result"].get("title", media_path.stem),
            "transcript": transcription,
            "candidates": candidates,
        }

    try:
        job = job_manager.submit("analysis", worker)
    except RuntimeError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    return job_manager.get(job.id)


@router.post("/jobs/{job_id}/clips", status_code=202)
def generate_clips(job_id: str, request: GenerateRequest) -> dict[str, Any]:
    analysis_job = _job_or_404(job_id)
    result = analysis_job.get("result")
    if analysis_job["type"] != "analysis" or analysis_job["status"] != "completed" or not result:
        raise HTTPException(status_code=409, detail="Completed analysis is required before rendering")

    source_path = Path(result["source_path"])
    if not source_path.is_file():
        raise HTTPException(status_code=410, detail="Source media is no longer available")

    def worker(context: JobContext) -> dict[str, Any]:
        clips = render_clips(
            source=source_path,
            specs=request.clips,
            transcript=result["transcript"],
            request=request,
            source_title=result["source_title"],
            context=context,
        )
        return {"clips": clips}

    try:
        job = job_manager.submit("render", worker)
    except RuntimeError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    return job_manager.get(job.id)


@router.get("/clips/{filename}")
def get_clip(filename: str):
    settings = get_settings()
    safe_name = Path(filename).name
    path = (settings.clips_dir.resolve() / safe_name).resolve()
    if path.parent != settings.clips_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")
    from fastapi.responses import FileResponse

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name,
        content_disposition_type="inline",
    )
