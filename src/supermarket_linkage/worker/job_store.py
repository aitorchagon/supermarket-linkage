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
    List,
    Dict, 
    Optional,
    Union,
)

from supermarket_linkage.consts import JOB_TTL_SECONDS
from supermarket_linkage.worker.consts import (
    STATUS_QUEUED,
)



@dataclass
class JobProgress:
    """
    This class represents the payload of the running job (done, total, status).
    """

    done: int = 0
    total: int = 0
    status: str = STATUS_QUEUED

    def as_dict(self) -> Dict[str, Union[int, str]]:
        return {"done": self.done, "total": self.total, "status": self.status}

@dataclass
class JobRecord:
    """
    This is the record for one linkage job, it does not store any data after its creation.
    """

    id: str
    status: str
    progress: JobProgress
    created_at: float = 0.0
    updated_at: float = 0.0
    warnings: List[str] = field(default_factory=list)
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class JobStore(ABC):
    """
    This class allows to create, read or update jobs and expired records
    are treated as missing.
    """

    @abstractmethod
    def create(self, job: JobRecord) -> None:
        """
        This function allows to create a job, where job.id is unique. 
        """

    @abstractmethod
    def get(self, job_id: str) -> Optional[JobRecord]:
        """
        This function returns a copy of a job or None if it expired or it is missing.
        """

    @abstractmethod
    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: JobProgress | None = None,
        warnings: Optional[List[str]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ) -> Optional[JobRecord]:
        """
        This function allows to patch fields on an existing job. 
        It returns None if the job is missing or it has expired.
        """


class InMemoryJobStore(JobStore):
    """
    This class is a process-local dict with job_ttl_seconds timeline. It is not 
    shared across replicas. This is the previous version for a future Redis database 
    for distributed computing, in case we need to scale this.
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
