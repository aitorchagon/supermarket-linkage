from __future__ import annotations

from typing import List
import time

from fastapi.testclient import TestClient

from tests.benchmark.latency_harness import (
    FAIL_COLD_WARMUP_S,
    FAIL_HOT_10_P50_S,
    LINES_10,
    N_HOT_10,
    SLO_COLD_WARMUP_P95_S,
    SLO_HOT_10_P50_S,
    WARN_COLD_WARMUP_S,
    WARN_HOT_10_P50_S,
    check_p50,
    check_p95,
    cold_warmup_client,
    measure_hot_jobs,
    paste,
)


def test_hot_10_line_job_p50_sample_catalog(sample_client: TestClient) -> None:
    """Warm worker, sample catalog: p50 must stay under the mock fail cap."""
    assert len(LINES_10) == 10
    text = paste(LINES_10)
    cold_s, hot = measure_hot_jobs(sample_client, text, N_HOT_10)
    print(f"10-line sample catalog cold first job={cold_s:.3f}s")
    check_p50(
        hot,
        fail_s=FAIL_HOT_10_P50_S,
        warn_s=WARN_HOT_10_P50_S,
        slo_s=SLO_HOT_10_P50_S,
        label="hot 10-line sample catalog",
    )


def test_hot_10_line_job_p50_mocked_http(mocked_http_client: TestClient) -> None:
    """Warm worker, Algolia mocked from sample_catalog.json (sleep_s=0)."""
    text = paste(LINES_10)
    cold_s, hot = measure_hot_jobs(mocked_http_client, text, N_HOT_10)
    print(f"10-line mocked HTTP cold first job={cold_s:.3f}s")
    check_p50(
        hot,
        fail_s=FAIL_HOT_10_P50_S,
        warn_s=WARN_HOT_10_P50_S,
        slo_s=SLO_HOT_10_P50_S,
        label="hot 10-line mocked HTTP",
    )


def test_cold_warmup_sample_backend() -> None:
    """POST /warmup with TokenOverlap (not MiniLM). Plan SLO is 90s p95 for real load."""
    samples: List[float] = []
    for _ in range(3):
        with cold_warmup_client() as client:
            assert client.get("/health").json()["warm"] is False
            t0 = time.perf_counter()
            response = client.post("/warmup")
            elapsed = time.perf_counter() - t0
            assert response.status_code == 200, response.text
            assert response.json()["warm"] is True
            samples.append(elapsed)
    print(f"cold warmup (sample backend) samples={[f'{x:.3f}' for x in samples]}")
    check_p50(
        samples,
        fail_s=FAIL_COLD_WARMUP_S,
        warn_s=WARN_COLD_WARMUP_S,
        slo_s=SLO_COLD_WARMUP_P95_S,
        label="cold /warmup sample backend",
    )
    check_p95(samples, fail_s=FAIL_COLD_WARMUP_S, label="cold /warmup sample backend")
