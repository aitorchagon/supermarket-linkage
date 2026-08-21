from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from supermarket_linkage.consts import MAX_JOBS_PER_HOUR, MAX_LINES
from supermarket_linkage.worker.api import create_app
from supermarket_linkage.worker.rate_limiter import RateLimiter
from supermarket_linkage.worker.settings import WorkerSettings
from supermarket_linkage.worker.warmup import ModelRegistry, TokenOverlapEmbedder


@pytest.fixture
def settings() -> WorkerSettings:
    return WorkerSettings(
        api_key=None,
        use_sample_catalog=True,
        skip_model_preload=True,
        sample_catalog_path=None,
    )


@pytest.fixture
def client(settings: WorkerSettings) -> Iterator[TestClient]:
    app = create_app(
        settings=settings,
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["use_sample_catalog"] is True
    assert "warm" in body


def test_warmup(client: TestClient) -> None:
    response = client.post("/warmup")
    assert response.status_code == 200
    body = response.json()
    assert body["warm"] is True
    assert client.get("/health").json()["warm"] is True


def test_jobs_validation_empty_400(client: TestClient) -> None:
    response = client.post(
        "/jobs",
        json={"text": "\n\n  ", "store": "mercadona", "postal_code": "28001"},
    )
    assert response.status_code == 400
    assert "detail" in response.json()


def test_jobs_validation_too_many_lines_400(client: TestClient) -> None:
    text = "\n".join(f"item {i}" for i in range(MAX_LINES + 1))
    response = client.post(
        "/jobs",
        json={"text": text, "store": "mercadona", "postal_code": "28001"},
    )
    assert response.status_code == 400
    assert "Too many lines" in response.json()["detail"]


def test_jobs_invalid_postal_400(client: TestClient) -> None:
    response = client.post(
        "/jobs",
        json={"text": "leche entera 1l", "store": "mercadona", "postal_code": "28O01"},
    )
    assert response.status_code == 400
    assert "postal" in response.json()["detail"].lower()


def test_jobs_unknown_store_400(client: TestClient) -> None:
    response = client.post(
        "/jobs",
        json={"text": "leche entera 1l", "store": "dia", "postal_code": "28001"},
    )
    assert response.status_code == 400


def test_jobs_rate_limit_429(settings: WorkerSettings) -> None:
    app = create_app(
        settings=settings,
        rate_limiter=RateLimiter(max_jobs_per_hour=1),
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
    )
    with TestClient(app) as client:
        body = {"text": "leche entera 1l", "store": "mercadona", "postal_code": "28001"}
        first = client.post("/jobs", json=body)
        assert first.status_code == 202
        second = client.post("/jobs", json=body)
        assert second.status_code == 429
        assert "rate limit" in second.json()["detail"].lower()


def test_jobs_happy_path_sample_catalog(client: TestClient) -> None:
    created = client.post(
        "/jobs",
        json={
            "text": "arroz basmati 1500 g",
            "store": "mercadona",
            "postal_code": "28001",
            "is_promo_member": False,
        },
    )
    assert created.status_code == 202
    payload = created.json()
    job_id = payload["id"]
    assert payload["progress"] == {"done": 0, "total": 1, "status": "queued"}

    fetched = client.get(f"/jobs/{job_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "done"
    assert body["progress"]["done"] == 1
    assert body["progress"]["total"] == 1
    assert body["progress"]["status"] == "done"
    assert body["results"] and len(body["results"]) == 1
    row = body["results"][0]
    assert row["product_id"] == "4245"
    assert row["units_needed"] == 2
    assert row["status"] == "matched"


def test_jobs_missing_404(client: TestClient) -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404


def test_jobs_rate_limit_ignores_spoofed_forwarded_for(settings: WorkerSettings) -> None:
    app = create_app(
        settings=settings,
        rate_limiter=RateLimiter(max_jobs_per_hour=1),
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
    )
    body = {"text": "leche entera 1l", "store": "mercadona", "postal_code": "28001"}
    with TestClient(app) as client:
        first = client.post("/jobs", json=body, headers={"X-Forwarded-For": "1.1.1.1"})
        assert first.status_code == 202
        second = client.post("/jobs", json=body, headers={"X-Forwarded-For": "8.8.8.8"})
        assert second.status_code == 429


def test_api_key_required() -> None:
    settings = WorkerSettings(
        api_key="secret",
        use_sample_catalog=True,
        skip_model_preload=True,
        sample_catalog_path=None,
    )
    app = create_app(
        settings=settings,
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
    )
    job_body = {"text": "leche entera 1l", "store": "mercadona", "postal_code": "28001"}
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/warmup").status_code == 401
        assert client.post("/jobs", json=job_body).status_code == 401
        assert client.get("/jobs/x").status_code == 401
        assert client.post("/warmup", headers={"X-API-Key": "secret"}).status_code == 200
        created = client.post("/jobs", json=job_body, headers={"WORKER_API_KEY": "secret"})
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert client.get(f"/jobs/{job_id}").status_code == 401
        fetched = client.get(f"/jobs/{job_id}", headers={"WORKER-API-KEY": "secret"})
        assert fetched.status_code == 200


def test_default_max_jobs_constant_used_by_limiter() -> None:
    # Guard: threat-model cap still 5/h so the 429 test's override is meaningful.
    assert MAX_JOBS_PER_HOUR == 5
