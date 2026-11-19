import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger

from backend.config import get_settings


@dataclass
class Job:
    id: str
    type: str
    status: str = "queued"
    progress: float = 0
    stage: str = "Queued"
    message: str = "Waiting for a worker"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: dict[str, Any] | None = None
    error: str | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)


class JobContext:
    def __init__(self, manager: "JobManager", job_id: str) -> None:
        self.manager = manager
        self.job_id = job_id

    @property
    def cancelled(self) -> bool:
        return self.manager.cancel_event(self.job_id).is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled("Job cancelled by user")

    def update(
        self,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        self.manager.update(
            self.job_id,
            progress=progress,
            stage=stage,
            message=message,
        )


class JobCancelled(Exception):
    pass


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=get_settings().max_workers,
            thread_name_prefix="clipper",
        )

    def submit(self, job_type: str, worker: Callable[[JobContext], dict[str, Any]]) -> Job:
        with self._lock:
            active = sum(job.status in {"queued", "running"} for job in self._jobs.values())
            if active >= get_settings().max_workers + 8:
                raise RuntimeError("Processing queue is full; wait for an active job to finish")
            if len(self._jobs) >= 100:
                completed = [
                    job_id
                    for job_id, job in self._jobs.items()
                    if job.status in {"completed", "failed", "cancelled"}
                ]
                for old_id in completed[: len(self._jobs) - 80]:
                    self._jobs.pop(old_id, None)
                    self._futures.pop(old_id, None)
            job = Job(id=str(uuid.uuid4()), type=job_type)
            self._jobs[job.id] = job
            self._futures[job.id] = self._executor.submit(self._run, job.id, worker)
            return job

    def _run(self, job_id: str, worker: Callable[[JobContext], dict[str, Any]]) -> None:
        self.update(job_id, status="running", stage="Starting", message="Processing started")
        try:
            result = worker(JobContext(self, job_id))
            if self.cancel_event(job_id).is_set():
                if self._jobs[job_id].type == "recording" and result.get("partial"):
                    with self._lock:
                        self._jobs[job_id].result = result
                    self.update(
                        job_id,
                        status="completed",
                        progress=100,
                        stage="Recording stopped",
                        message="Partial live recording saved",
                    )
                else:
                    self.update(
                        job_id,
                        status="cancelled",
                        stage="Cancelled",
                        message="Job cancelled",
                    )
            else:
                with self._lock:
                    job = self._jobs[job_id]
                    job.result = result
                self.update(
                    job_id,
                    status="completed",
                    progress=100,
                    stage="Complete",
                    message="Processing completed",
                )
        except JobCancelled as error:
            self.update(
                job_id,
                status="cancelled",
                stage="Cancelled",
                message=str(error),
            )
        except Exception as error:
            if self.cancel_event(job_id).is_set():
                self.update(
                    job_id,
                    status="cancelled",
                    stage="Cancelled",
                    message="Job cancelled",
                )
                return
            logger.exception("Job {} ({}) failed", job_id, self._jobs[job_id].type)
            self.update(
                job_id,
                status="failed",
                stage="Failed",
                message="Processing failed",
                error=str(error),
            )

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = max(0, min(100, progress))
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def cancel_event(self, job_id: str) -> threading.Event:
        with self._lock:
            return self._jobs[job_id]._cancel

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in {"queued", "running"}:
                return False
            job._cancel.set()
            future = self._futures.get(job_id)
            if future and future.cancel():
                job.status = "cancelled"
                job.stage = "Cancelled"
                job.message = "Cancelled before processing started"
                job.updated_at = datetime.now(timezone.utc).isoformat()
            return True

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._serialize(job) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._serialize(job) for job in self._jobs.values()]

    @staticmethod
    def _serialize(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "message": job.message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "result": job.result,
            "error": job.error,
        }


job_manager = JobManager()
