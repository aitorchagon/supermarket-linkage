"""In-process per-IP token-bucket rate limits (Decision 14)."""

from __future__ import annotations

import threading
import time
from typing import Callable

from supermarket_linkage.consts import (
    MAX_CONCURRENT_JOBS_PER_IP,
    MAX_JOBS_PER_HOUR,
    MAX_WARMUP_PER_HOUR,
)

SECONDS_PER_HOUR = 3600.0


class _TokenBucket:
    """Fixed-capacity bucket that refills continuously over time."""

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        *,
        now: Callable[[], float],
    ) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_per_second = refill_per_second
        self._now = now
        self._updated_at = now()

    def try_consume(self, amount: float = 1.0) -> bool:
        """Consume ``amount`` tokens if available.

        Pre: ``amount`` > 0.
        Post: True and tokens decreased iff enough tokens after refill.
        """
        self._refill()
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True

    def _refill(self) -> None:
        now = self._now()
        elapsed = now - self._updated_at
        if elapsed > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_per_second,
            )
            self._updated_at = now


class RateLimiter:
    """Per-IP warmup/job quotas and concurrent job slots.

    Limits come from ``consts`` (warmup/hour, jobs/hour, max concurrent).
    State is in-process only; resets on worker restart.
    """

    def __init__(
        self,
        *,
        now: Callable[[], float] | None = None,
        max_warmup_per_hour: int = MAX_WARMUP_PER_HOUR,
        max_jobs_per_hour: int = MAX_JOBS_PER_HOUR,
        max_concurrent_jobs: int = MAX_CONCURRENT_JOBS_PER_IP,
    ) -> None:
        self._now = now or time.monotonic
        self._max_warmup = max_warmup_per_hour
        self._max_jobs = max_jobs_per_hour
        self._max_concurrent = max_concurrent_jobs
        self._warmup: dict[str, _TokenBucket] = {}
        self._jobs: dict[str, _TokenBucket] = {}
        self._inflight: dict[str, int] = {}
        self._lock = threading.Lock()

    def allow_warmup(self, ip: str) -> bool:
        """Try to take one warmup token for ``ip``.

        Pre: ``ip`` is a non-empty client identifier.
        Post: True iff under the hourly warmup cap after consume.
        """
        with self._lock:
            bucket = self._warmup.get(ip)
            if bucket is None:
                bucket = _TokenBucket(
                    self._max_warmup,
                    self._max_warmup / SECONDS_PER_HOUR,
                    now=self._now,
                )
                self._warmup[ip] = bucket
            return bucket.try_consume()

    def allow_job(self, ip: str) -> bool:
        """Try to take one job token for ``ip`` (hourly quota only).

        Pre: ``ip`` is a non-empty client identifier.
        Post: True iff under the hourly job cap after consume.
        Does not acquire a concurrent slot — call ``try_acquire_job`` for that.
        """
        with self._lock:
            bucket = self._jobs.get(ip)
            if bucket is None:
                bucket = _TokenBucket(
                    self._max_jobs,
                    self._max_jobs / SECONDS_PER_HOUR,
                    now=self._now,
                )
                self._jobs[ip] = bucket
            return bucket.try_consume()

    def try_acquire_job(self, ip: str) -> bool:
        """Reserve a concurrent job slot for ``ip`` if free.

        Pre: ``ip`` is a non-empty client identifier.
        Post: True and inflight incremented iff under ``max_concurrent_jobs``.
        """
        with self._lock:
            current = self._inflight.get(ip, 0)
            if current >= self._max_concurrent:
                return False
            self._inflight[ip] = current + 1
            return True

    def release_job(self, ip: str) -> None:
        """Release one concurrent job slot for ``ip``.

        Pre: a matching successful ``try_acquire_job`` for ``ip``.
        Post: inflight for ``ip`` decreased by one (floor 0).
        """
        with self._lock:
            current = self._inflight.get(ip, 0)
            if current <= 1:
                self._inflight.pop(ip, None)
            else:
                self._inflight[ip] = current - 1

    def allow_and_acquire_job(self, ip: str) -> bool:
        """Consume a job token and acquire a concurrent slot atomically.

        Pre: ``ip`` is a non-empty client identifier.
        Post: True iff both hourly quota and concurrent slot succeed.
        On failure neither token nor slot is kept.
        """
        with self._lock:
            bucket = self._jobs.get(ip)
            if bucket is None:
                bucket = _TokenBucket(
                    self._max_jobs,
                    self._max_jobs / SECONDS_PER_HOUR,
                    now=self._now,
                )
                self._jobs[ip] = bucket

            current = self._inflight.get(ip, 0)
            if current >= self._max_concurrent:
                return False
            if not bucket.try_consume():
                return False
            self._inflight[ip] = current + 1
            return True
