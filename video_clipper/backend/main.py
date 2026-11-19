from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import get_settings
from backend.routes.health import router as health_router
from backend.routes.media import router as media_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    for folder in (
        settings.downloads_dir,
        settings.clips_dir,
        settings.temp_dir,
        settings.logs_dir,
        settings.model_cache_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    logger.add(settings.logs_dir / "video-clipper.log", rotation="10 MB", retention=5)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(media_router)

frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")
