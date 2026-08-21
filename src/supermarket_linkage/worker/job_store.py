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
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

from supermarket_linkage.consts import JOB_TTL_SECONDS
from supermarket_linkage.worker.consts import STATUS_QUEUED

# Re-export for callers/tests that import status from this module.
__all__ = [
    "JobProgress",
    "JobRecord",
    "JobStore",
    "InMemoryJobStore",
    "STATUS_QUEUED",
]

@dataclass
class JobProgress:
    """Payload of a running job (done, total, status)."""

    done: int = 0
    total: int = 0
    status: str = STATUS_QUEUED

    def as_dict(self) -> Dict[str, Union[int, str]]:
        return {"done": self.done, "total": self.total, "status": self.status}


@dataclass
class JobRecord:
    """
    One linkage job record. Does not store the original paste after creation.
    """

    id: str
    status: str
    progress: JobProgress
    created_at: float = 0.0
    updated_at: float = 0.0
    warnings: List[str] = field(default_factory=list)
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    matched_count: Optional[int] = None
    no_match_count: Optional[int] = None
    unmatched_queries: Optional[List[str]] = None


class JobStore(ABC):
    """Create, read, or update jobs; expired records are treated as missing."""

    @abstractmethod
    def create(self, job: JobRecord) -> None:
        """Create a job; ``job.id`` must be unique."""

    @abstractmethod
    def get(self, job_id: str) -> Optional[JobRecord]:
        """Return a copy of a job, or None if expired / missing."""

    @abstractmethod
    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[JobProgress] = None,
        warnings: Optional[List[str]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        matched_count: Optional[int] = None,
        no_match_count: Optional[int] = None,
        unmatched_queries: Optional[List[str]] = None,
    ) -> Optional[JobRecord]:
        """Patch fields on an existing job. None if missing or expired."""


class InMemoryJobStore(JobStore):
    """
    Process-local dict with TTL. Not shared across replicas.
    Placeholder until a Redis-backed store if we scale out.
    """

    def __init__(
        self,
        ttl_s: int = JOB_TTL_SECONDS,
        *,
        now: Optional[Callable[[], float]] = None,
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

    def get(self, job_id: str) -> Optional[JobRecord]:
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
        status: Optional[str] = None,
        progress: Optional[JobProgress] = None,
        warnings: Optional[List[str]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        matched_count: Optional[int] = None,
        no_match_count: Optional[int] = None,
        unmatched_queries: Optional[List[str]] = None,
    ) -> Optional[JobRecord]:
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
            if matched_count is not None:
                job.matched_count = matched_count
            if no_match_count is not None:
                job.no_match_count = no_match_count
            if unmatched_queries is not None:
                job.unmatched_queries = list(unmatched_queries)
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
        unmatched_queries=(
            list(job.unmatched_queries) if job.unmatched_queries is not None else None
        ),
    )
