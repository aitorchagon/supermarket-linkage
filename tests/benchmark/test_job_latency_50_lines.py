"""Hot 50-line job latency (sample catalog + mocked HTTP). No live Mercadona / MiniLM."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.benchmark.latency_harness import (
    FAIL_HOT_50_P50_S,
    LINES_50,
    N_HOT_50,
    SLO_HOT_50_P95_S,
    WARN_HOT_50_P50_S,
    check_p50,
    check_p95,
    measure_hot_jobs,
    paste,
)


def test_hot_50_line_job_p50_sample_catalog(sample_client: TestClient) -> None:
    """Warm worker, sample catalog. Plan: p95 ≤ 5 min live; mock p50 fail at 60s."""
    assert len(LINES_50) == 50
    text = paste(LINES_50)
    cold_s, hot = measure_hot_jobs(sample_client, text, N_HOT_50)
    print(f"50-line sample catalog cold first job={cold_s:.3f}s")
    check_p50(
        hot,
        fail_s=FAIL_HOT_50_P50_S,
        warn_s=WARN_HOT_50_P50_S,
        slo_s=SLO_HOT_50_P95_S,
        label="hot 50-line sample catalog",
    )
    check_p95(hot, fail_s=SLO_HOT_50_P95_S, label="hot 50-line sample catalog")


def test_hot_50_line_job_p50_mocked_http(mocked_http_client: TestClient) -> None:
    """Warm worker, Algolia mocked from sample_catalog.json (sleep_s=0)."""
    text = paste(LINES_50)
    cold_s, hot = measure_hot_jobs(mocked_http_client, text, N_HOT_50)
    print(f"50-line mocked HTTP cold first job={cold_s:.3f}s")
    check_p50(
        hot,
        fail_s=FAIL_HOT_50_P50_S,
        warn_s=WARN_HOT_50_P50_S,
        slo_s=SLO_HOT_50_P95_S,
        label="hot 50-line mocked HTTP",
    )
    check_p95(hot, fail_s=SLO_HOT_50_P95_S, label="hot 50-line mocked HTTP")
