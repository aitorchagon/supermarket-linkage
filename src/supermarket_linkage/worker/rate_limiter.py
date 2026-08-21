from __future__ import annotations

import threading
import time
from typing import (
    Callable,
    Optional,
    Dict,
)

from supermarket_linkage.consts import (
    MAX_CONCURRENT_JOBS_PER_IP,
    MAX_JOBS_PER_HOUR,
    MAX_WARMUP_PER_HOUR,
)
from supermarket_linkage.worker.consts import (
    SECONDS_PER_HOUR
)



class _TokenBucket:
    """
    This is a fixed-capacity token bucket per IP that is refilled continously over time.
    """

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

    def consume_tokens(self, amount: float = 1.0) -> bool:
        """
        This function allows to consume 'amount' tokens if they are available.
        Previosuly, we have a determnined amount; if and only if we have enough tokens
        after refill, tokens are decreased. We return True in that case, and False otherwise.
        """
        self._refill()
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True

    def _refill(self) -> None:
        """
        This function updates the timestamp of token update, and the amount of tokens that we have available
        to consume. 
        """
        now = self._now()
        elapsed = now - self._updated_at
        if elapsed > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_per_second,
            )
            self._updated_at = now


class RateLimiter:
    """
    This class provides per-ip warmup and job quotas, as well as
    concurrent job slots. The limits are coming from consts, they reset
    when the worker restart.
    """

    def __init__(
        self,
        *,
        now: Optional[Callable[[], float]] = None,
        max_warmup_per_hour: int = MAX_WARMUP_PER_HOUR,
        max_jobs_per_hour: int = MAX_JOBS_PER_HOUR,
        max_concurrent_jobs: int = MAX_CONCURRENT_JOBS_PER_IP,
    ) -> None:
        self._now = now or time.monotonic
        self._max_warmup = max_warmup_per_hour
        self._max_jobs = max_jobs_per_hour
        self._max_concurrent = max_concurrent_jobs
        self._warmup: Dict[str, _TokenBucket] = {}
        self._jobs: Dict[str, _TokenBucket] = {}
        self._inflight: Dict[str, int] = {}
        self._lock = threading.Lock()

    def allow_warmup(self, ip: str) -> bool:
        """
        This function takes one warmup token for 'ip'. We return True if and only of
        we are under the hourly warmup cap after consume, otherwise False. The 'ip' is a non-empty
        client identifier.
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
            return bucket.consume_tokens()

    def allow_job(self, ip: str) -> bool:
        """
        This function takes one job token for an ip, with an associated
        hourly quota. We return True if and only if we are under the hourly job cap after consume.
        We do not acquite a concurrent slot.
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
            return bucket.consume_tokens()

    def reserve_concurrent_job(self, ip: str) -> bool:
        """
        This function reserves a concurrent job slot for 'ip' if it is free. 
        We return True and we increment inflight if and only if we are under max_concurrent_jobs. Inflight
        measures instatenous concurrency (the number of active jobs a specific IP is executing at the exact moment), as
        contrasted with _jobs and _warmup, which measure overall usage of a single client (track request volume against
        hourly quotas).
        """
        with self._lock:
            current = self._inflight.get(ip, 0)
            if current >= self._max_concurrent:
                return False
            self._inflight[ip] = current + 1
            return True

    def release_job(self, ip: str) -> None:
        """
        This function releases one concurrent job slot for an ip. The inflight for that ip
        is decrease by one.
        """
        with self._lock:
            current = self._inflight.get(ip, 0)
            if current <= 1:
                self._inflight.pop(ip, None)
            else:
                self._inflight[ip] = current - 1

    def consume_job(self, ip: str) -> bool:
        """
        Consume a job token and acquire a concurrent slot atomically.
        Returns True only if both hourly quota and concurrent slot succeed.
        On failure, neither is kept.
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
            if not bucket.consume_tokens():
                return False
            self._inflight[ip] = current + 1
            return True

    def allow_and_acquire_job(self, ip: str) -> bool:
        """Alias for ``consume_job`` (hourly quota + concurrent slot)."""
        return self.consume_job(ip)

    def try_acquire_job(self, ip: str) -> bool:
        """Alias for ``reserve_concurrent_job`` (concurrent slot only)."""
        return self.reserve_concurrent_job(ip)