
from supermarket_linkage.consts import JOB_TTL_SECONDS
from supermarket_linkage.worker.job_store import (
    STATUS_QUEUED,
    InMemoryJobStore,
    JobProgress,
    JobRecord,
)


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _job(job_id: str, created_at: float) -> JobRecord:
    return JobRecord(
        id=job_id,
        status=STATUS_QUEUED,
        progress=JobProgress(done=0, total=1, status=STATUS_QUEUED),
        created_at=created_at,
        updated_at=created_at,
    )


def test_get_missing_is_none() -> None:
    store = InMemoryJobStore(now=_FakeClock())
    assert store.get("missing") is None


def test_create_get_and_update() -> None:
    clock = _FakeClock()
    store = InMemoryJobStore(now=clock)
    store.create(_job("a", created_at=0.0))
    got = store.get("a")
    assert got is not None
    assert got.status == STATUS_QUEUED
    updated = store.update("a", status="running")
    assert updated is not None
    assert updated.status == "running"
    assert store.get("a") is not None
    assert store.get("a").status == "running"


def test_create_stamps_store_clock_not_caller_created_at() -> None:
    clock = _FakeClock()
    store = InMemoryJobStore(ttl_s=JOB_TTL_SECONDS, now=clock)
    store.create(_job("a", created_at=999_999.0))
    assert store.get("a") is not None
    clock.advance(JOB_TTL_SECONDS)
    assert store.get("a") is None


def test_get_returns_independent_copy() -> None:
    clock = _FakeClock()
    store = InMemoryJobStore(now=clock)
    store.create(_job("a", created_at=0.0))
    first = store.get("a")
    assert first is not None
    first.status = "mutated"
    first.progress.done = 99
    second = store.get("a")
    assert second is not None
    assert second.status == STATUS_QUEUED
    assert second.progress.done == 0
