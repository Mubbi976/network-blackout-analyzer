from contextlib import closing, contextmanager
import json
import sqlite3
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

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
    def __init__(self, database_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._database_path = database_path
        self._executor = ThreadPoolExecutor(
            max_workers=get_settings().max_workers,
            thread_name_prefix="clipper",
        )
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_database()
            self._load_jobs()

    def _connect(self) -> sqlite3.Connection:
        if self._database_path is None:
            raise RuntimeError("Job persistence is not configured")
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as connection:
            with connection:
                yield connection

    def _initialize_database(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )

    def _load_jobs(self) -> None:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        for row in reversed(rows):
            job = Job(
                id=row["id"],
                type=row["type"],
                status=row["status"],
                progress=row["progress"],
                stage=row["stage"],
                message=row["message"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                result=json.loads(row["result_json"]) if row["result_json"] else None,
                error=row["error"],
            )
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.stage = "Interrupted"
                job.message = "Processing was interrupted when the server restarted"
                job.error = job.message
                job.updated_at = datetime.now(timezone.utc).isoformat()
            self._jobs[job.id] = job
            self._persist(job)

    def _persist(self, job: Job) -> None:
        if self._database_path is None:
            return
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, type, status, progress, stage, message, created_at,
                    updated_at, result_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    progress = excluded.progress,
                    stage = excluded.stage,
                    message = excluded.message,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json,
                    error = excluded.error
                """,
                (
                    job.id,
                    job.type,
                    job.status,
                    job.progress,
                    job.stage,
                    job.message,
                    job.created_at,
                    job.updated_at,
                    json.dumps(job.result) if job.result is not None else None,
                    job.error,
                ),
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
                    if self._database_path is not None:
                        with self._connection() as connection:
                            connection.execute("DELETE FROM jobs WHERE id = ?", (old_id,))
            job = Job(id=str(uuid.uuid4()), type=job_type)
            self._jobs[job.id] = job
            self._persist(job)
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
            self._persist(job)

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
                self._persist(job)
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


job_manager = JobManager(database_path=get_settings().jobs_db_path)
