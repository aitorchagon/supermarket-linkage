from __future__ import annotations

import json
import time
import warnings
from typing import (
    Set,
    Tuple,
    List,
    Dict,
    Union,
    Generator,
)
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient
from supermarket_linkage.consts import (
    MERCADONA_ALGOLIA_HOST, 
    MERCADONA_ALGOLIA_QUERIES_PATH,
)
from supermarket_linkage.preprocessors.text_normalizer import (
    extract_search_query, 
    normalize_text,
)
from supermarket_linkage.worker.api import create_app
from supermarket_linkage.worker.rate_limiter import RateLimiter
from supermarket_linkage.worker.settings import WorkerSettings
from supermarket_linkage.worker.warmup import (
    ModelRegistry, 
    TokenOverlapEmbedder, 
)

# --- Planned SLOs, mock path must beat these ones ---
SLO_COLD_WARMUP_P95_S = 90.0
SLO_HOT_10_P50_S = 60.0
SLO_HOT_50_P95_S = 300.0

# Fail if mock p50 is already in live-SLO territory (pipeline too slow offline).
FAIL_COLD_WARMUP_S = 5.0
FAIL_HOT_10_P50_S = 15.0
FAIL_HOT_50_P50_S = 60.0

WARN_COLD_WARMUP_S = 1.0
WARN_HOT_10_P50_S = 5.0
WARN_HOT_50_P50_S = 20.0

N_HOT_10 = 7
N_HOT_50 = 5

_ALGOLIA_URL = f"{MERCADONA_ALGOLIA_HOST}{MERCADONA_ALGOLIA_QUERIES_PATH}"
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_catalog.json"

# User-style lines covering the sample catalog (plus a few no-matches).
LINES_10: Tuple[str] = (
    "arroz basmati 1500 g",
    "leche entera 1l",
    "huevos camperos",
    "aceite de oliva virgen extra 1l",
    "pan de molde blanco",
    "pasta espagueti 500 g",
    "yogur natural",
    "platano de canarias",
    "pollo entero",
    "azucar blanco 1 kg",
)

LINES_50: Tuple[str] = LINES_10 + (
    "arroz redondo 1 kg",
    "arroz integral 1 kg",
    "leche semidesnatada 1l",
    "leche desnatada 1l",
    "aceite de oliva suave 1l",
    "aceite de girasol 1l",
    "huevos frescos",
    "pan de molde integral",
    "pasta espirales 500 g",
    "pasta macarrones 500 g",
    "tomate frito",
    "tomate triturado",
    "atun claro en aceite de oliva",
    "atun claro al natural",
    "yogur griego",
    "queso fresco batido",
    "queso semicurado lonchas",
    "manzana golden",
    "naranja de mesa",
    "pechuga de pollo",
    "jamon cocido lonchas",
    "cafe molido mezcla",
    "cafe molido natural",
    "sal marina fina",
    "harina de trigo",
    "garbanzos cocidos",
    "lentejas cocidas",
    "detergente liquido",
    "papel higienico",
    "agua mineral",
    "cerveza clasica",
    "mantequilla sin sal",
    "chocolate negro",
    "arroz basmati 500 g",
    "leche entera 2l",
    "aceite de oliva 1l",
    "pan integral",
    "salsa de soja premium inexistente",
    "quinoa organica inexistente",
    "kombucha artesanal inexistente",
)

_UNIT_TO_FORMAT = {"KILO": "kg", "LITRO": "l", "UNIDAD": "ud"}


def percentile(values: List[float], p: float) -> float:
    """Linear interpolation percentile."""
    if not values:
        raise ValueError("percentile() on empty sample")
    ordered = sorted(values)
    if p <= 0:
        return ordered[0]
    if p >= 100:
        return ordered[-1]
    rank = (len(ordered) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def check_p50(
    samples: List[float],
    *,
    fail_s: float,
    warn_s: float,
    slo_s: float,
    label: str,
) -> float:
    """Print p50; fail if mock p50 is wild; warn if elevated."""
    p50 = percentile(samples, 50)
    p95 = percentile(samples, 95)
    raw = ", ".join(f"{x:.3f}" for x in samples)
    print(f"{label}: p50={p50:.3f}s p95={p95:.3f}s n={len(samples)} samples=[{raw}]")
    if p50 > fail_s:
        pytest.fail(
            f"{label} p50={p50:.3f}s exceeds mock fail threshold {fail_s:.0f}s "
            f"(plan SLO {slo_s:.0f}s). samples=[{raw}]"
        )
    if p50 > warn_s:
        warnings.warn(
            f"{label} p50={p50:.3f}s exceeds mock warn threshold {warn_s:.0f}s "
            f"(plan SLO {slo_s:.0f}s)",
            stacklevel=2,
        )
    return p50


def check_p95(samples: List[float], *, fail_s: float, label: str) -> float:
    """Print p95; fail if mock p50 is wild; warn if elevated."""
    p95 = percentile(samples, 95)
    if p95 > fail_s:
        pytest.fail(f"{label} p95={p95:.3f}s exceeds {fail_s:.0f}s")
    return p95


def paste(lines: Tuple[str]) -> str:
    return "\n".join(lines)


def run_job(
        client: TestClient, 
        text: str, *, 
        timeout_s: float = 120.0,
    ) -> Tuple[float, Dict[str, Union[str, bool]]]:
    """Time POST /jobs until the record is terminal. TestClient runs tasks inline."""
    t0 = time.perf_counter()
    created = client.post(
        "/jobs",
        json={
            "text": text,
            "store": "mercadona",
            "postal_code": "28001",
            "is_promo_member": False,
        },
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]
    body = _wait_done(client, job_id, timeout_s=timeout_s)
    elapsed = time.perf_counter() - t0
    return elapsed, body


def _wait_done(client: TestClient, job_id: str, *, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"done", "error", "timeout"}:
            return last
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish; last={last}")


def measure_hot_jobs(client: TestClient, text: str, n_hot: int) -> Tuple[float, List[float]]:
    """One untimed warm job, then ``n_hot`` timed jobs. Returns (cold_s, hot_samples)."""
    cold_s, cold_body = run_job(client, text)
    assert cold_body["status"] == "done", cold_body.get("error")
    hot: List[float] = []
    for _ in range(n_hot):
        elapsed, body = run_job(client, text)
        assert body["status"] == "done", body.get("error")
        assert body["results"] is not None
        hot.append(elapsed)
    return cold_s, hot

@contextmanager
def sample_client() -> Generator[TestClient]:
    """Worker in sample-catalog mode"""
    app = create_app(
        settings=WorkerSettings(
            api_key=None,
            use_sample_catalog=True,
            skip_model_preload=False,
            sample_catalog_path=str(_FIXTURE),
        ),
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
        rate_limiter=RateLimiter(max_jobs_per_hour=100, max_warmup_per_hour=100),
    )
    with TestClient(app) as client:
        yield client

@contextmanager
def mocked_http_client() -> Generator[TestClient]:
    """Worker with Mercadona client; Algolia answered from sample_catalog.json."""
    hits = _sample_hits()
    transport = httpx.MockTransport(_make_handler(hits))
    http = httpx.Client(transport=transport, timeout=20.0)
    catalog = MercadonaCatalogClient(warehouse="mad1", http_client=http, sleep_s=0)
    app = create_app(
        settings=WorkerSettings(
            api_key=None,
            use_sample_catalog=False,
            skip_model_preload=True,
            sample_catalog_path=None,
        ),
        model_registry=ModelRegistry(backend="sample", embedder=TokenOverlapEmbedder()),
        catalog_client=catalog,
        rate_limiter=RateLimiter(max_jobs_per_hour=100, max_warmup_per_hour=100),
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        http.close()


@contextmanager
def cold_warmup_client() -> Generator[TestClient]:
    """Sample backend, embedder not preloaded — times POST /warmup."""
    app = create_app(
        settings=WorkerSettings(
            api_key=None,
            use_sample_catalog=True,
            skip_model_preload=True,
            sample_catalog_path=str(_FIXTURE),
        ),
        model_registry=ModelRegistry(backend="sample"),
        rate_limiter=RateLimiter(max_jobs_per_hour=100, max_warmup_per_hour=100),
    )
    with TestClient(app) as client:
        yield client


def _sample_hits() -> List[Tuple[Set[str], dict]]:
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    out: List[Tuple[Set[str], dict]] = []
    for row in rows:
        name = str(row.get("name") or "")
        tokens = set(normalize_text(name).split())
        out.append((tokens, _row_to_hit(row)))
    return out


def _row_to_hit(row: dict) -> dict:
    unit = str(row.get("unit_measure") or "UNIDAD")
    fmt = _UNIT_TO_FORMAT.get(unit, "ud")
    price = row.get("price_eur")
    promo = row.get("promo_price_eur")
    decreased = promo is not None and price is not None
    instructions = {
        "unit_price": promo if decreased else price,
        "previous_unit_price": price if decreased else None,
        "price_decreased": decreased,
        "reference_price": row.get("unit_price_eur") if row.get("unit_price_eur") is not None else price,
        "reference_format": fmt,
        "unit_size": row.get("approx_weight_kg") if row.get("approx_weight_kg") is not None else 1,
        "size_format": fmt,
    }
    return {
        "id": str(row.get("product_id") or ""),
        "display_name": row.get("name"),
        "brand": row.get("brand"),
        "share_url": row.get("url"),
        "price_instructions": instructions,
    }


def _make_handler(hits: List[Tuple[Set[str], dict]]):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "PUT":
            return httpx.Response(200, json={}, headers={"x-customer-wh": "mad1"})
        if request.method == "POST" and url.startswith(_ALGOLIA_URL.split("?")[0]):
            body = json.loads(request.content.decode("utf-8"))
            results = []
            for req in body.get("requests") or []:
                params = parse_qs(str(req.get("params") or ""))
                query = (params.get("query") or [""])[0]
                results.append({"hits": _hits_for(query, hits)})
            return httpx.Response(200, json={"results": results})
        return httpx.Response(404, json={"error": "unmocked"})

    return handler


def _hits_for(query: str, catalog: List[Tuple[Set[str], dict]]) -> List[dict]:
    tokens = [t for t in extract_search_query(query).split() if t]
    if not tokens:
        return []
    return [hit for name_tokens, hit in catalog if all(t in name_tokens for t in tokens)]
