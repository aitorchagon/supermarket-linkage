from supermarket_linkage.consts import (
    MAX_CONCURRENT_JOBS_PER_IP,
    MAX_JOBS_PER_HOUR,
    MAX_WARMUP_PER_HOUR,
)
from supermarket_linkage.worker.rate_limiter import RateLimiter


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_warmup_allows_up_to_hourly_cap() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(now=clock)
    ip = "1.1.1.1"
    for _ in range(MAX_WARMUP_PER_HOUR):
        assert limiter.allow_warmup(ip)
    assert not limiter.allow_warmup(ip)


def test_warmup_refills_after_hour() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(now=clock)
    ip = "1.1.1.1"
    for _ in range(MAX_WARMUP_PER_HOUR):
        assert limiter.allow_warmup(ip)
    assert not limiter.allow_warmup(ip)
    clock.advance(3600.0)
    assert limiter.allow_warmup(ip)


def test_jobs_allows_up_to_hourly_cap() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(now=clock)
    ip = "2.2.2.2"
    for _ in range(MAX_JOBS_PER_HOUR):
        assert limiter.allow_job(ip)
    assert not limiter.allow_job(ip)


def test_jobs_isolated_per_ip() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(now=clock)
    for _ in range(MAX_JOBS_PER_HOUR):
        assert limiter.allow_job("10.0.0.1")
    assert not limiter.allow_job("10.0.0.1")
    assert limiter.allow_job("10.0.0.2")


def test_concurrent_job_slot_one_per_ip() -> None:
    limiter = RateLimiter()
    ip = "3.3.3.3"
    assert MAX_CONCURRENT_JOBS_PER_IP == 1
    assert limiter.try_acquire_job(ip)
    assert not limiter.try_acquire_job(ip)
    limiter.release_job(ip)
    assert limiter.try_acquire_job(ip)


def test_allow_and_acquire_job_checks_both() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(now=clock)
    ip = "4.4.4.4"
    assert limiter.allow_and_acquire_job(ip)
    # Concurrent slot busy → fail without burning another token path oddly;
    # second call fails on concurrency while first slot still held.
    assert not limiter.allow_and_acquire_job(ip)
    limiter.release_job(ip)
    # Remaining hourly tokens: MAX_JOBS_PER_HOUR - 1
    for _ in range(MAX_JOBS_PER_HOUR - 1):
        assert limiter.allow_and_acquire_job(ip)
        limiter.release_job(ip)
    assert not limiter.allow_and_acquire_job(ip)


def test_release_job_idempotent_floor() -> None:
    limiter = RateLimiter()
    ip = "5.5.5.5"
    limiter.release_job(ip)  # no prior acquire
    assert limiter.try_acquire_job(ip)
