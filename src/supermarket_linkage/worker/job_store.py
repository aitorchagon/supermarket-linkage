"""Ephemeral job records (v1 in-memory; Redis later).

v1 uses ``InMemoryJobStore`` in one process. Restart drops in-flight jobs
(acceptable at this scale — DESIGN.md §5).

Migration: keep this ``JobStore`` ABC and the HTTP contract. Add
``RedisJobStore`` when 2+ replicas share state, job history must survive
restarts, or rate limits must be global. Do not change ``/jobs`` JSON.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from supermarket_linkage.consts import JOB_TTL_SECONDS

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_SEARCHING = "searching"
STATUS_LINKING = "linking"


@dataclass
class JobProgress:
    """Poll payload: ``{done, total, status}``."""

    done: int = 0
    total: int = 0
    status: str = STATUS_QUEUED

    def as_dict(self) -> dict[str, int | str]:
        return {"done": self.done, "total": self.total, "status": self.status}


@dataclass
class JobRecord:
    """One linkage job. Does not store the raw paste after create."""

    id: str
    status: str
    progress: JobProgress
    created_at: float = 0.0
    updated_at: float = 0.0
    warnings: List[str] = field(default_factory=list)
    results: List[dict[str, Any]] | None = None
    error: str | None = None


class JobStore(ABC):
    """Create / read / update jobs. Expired records are treated as missing."""

    @abstractmethod
    def create(self, job: JobRecord) -> None:
        """Insert ``job``. Pre: ``job.id`` is unique."""

    @abstractmethod
    def get(self, job_id: str) -> JobRecord | None:
        """Return a copy, or None if missing/expired."""

    @abstractmethod
    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: JobProgress | None = None,
        warnings: List[str] | None = None,
        results: List[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        """Patch fields on an existing job. None if missing/expired."""


class InMemoryJobStore(JobStore):
    """Process-local dict with ``JOB_TTL_SECONDS`` eviction.

    Not shared across replicas — swap for RedisJobStore without API changes.
    """

    def __init__(
        self,
        ttl_s: int = JOB_TTL_SECONDS,
        *,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._ttl_s = ttl_s
        self._now = now or time.monotonic
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, job: JobRecord) -> None:
        with self._lock:
            self._purge_unlocked()
            now = self._now()
            job.created_at = now
            job.updated_at = now
            self._jobs[job.id] = job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            self._purge_unlocked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return _copy_job(job)

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: JobProgress | None = None,
        warnings: List[str] | None = None,
        results: List[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        with self._lock:
            self._purge_unlocked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if warnings is not None:
                job.warnings = list(warnings)
            if results is not None:
                job.results = results
            if error is not None:
                job.error = error
            job.updated_at = self._now()
            return _copy_job(job)

    def _purge_unlocked(self) -> None:
        now = self._now()
        expired = [
            jid
            for jid, job in self._jobs.items()
            if now - job.created_at >= self._ttl_s
        ]
        for jid in expired:
            del self._jobs[jid]


def _copy_job(job: JobRecord) -> JobRecord:
    return replace(
        job,
        progress=replace(job.progress),
        warnings=list(job.warnings),
        results=list(job.results) if job.results is not None else None,
    )
