from __future__ import annotations

import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
)

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.validation.input_validator import is_valid_postal_code
from supermarket_linkage.worker.consts import API_KEY_HEADERS
from supermarket_linkage.worker.job_orchestrator import (
    JobOrchestrator,
    JobSpec,
    assert_supported_store,
)
from supermarket_linkage.worker.job_store import (
    STATUS_QUEUED,
    InMemoryJobStore,
    JobProgress,
    JobRecord,
    JobStore,
)
from supermarket_linkage.worker.logging_config import configure_logging
from supermarket_linkage.worker.rate_limiter import RateLimiter
from supermarket_linkage.worker.sample_catalog import SampleCatalogClient
from supermarket_linkage.worker.settings import WorkerSettings
from supermarket_linkage.worker.warmup import ModelRegistry

log = logging.getLogger(__name__)


class JobCreateBody(BaseModel):
    text: str
    store: str = "mercadona"
    postal_code: Optional[str] = None
    is_promo_member: bool = False


class ProgressBody(BaseModel):
    done: int
    total: int
    status: str


class JobCreateResponse(BaseModel):
    id: str
    status: str
    progress: ProgressBody
    warnings: List[str] = Field(default_factory=list)


class JobGetResponse(BaseModel):
    id: str
    status: str
    progress: ProgressBody
    warnings: List[str] = Field(default_factory=list)
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    matched_count: Optional[int] = None
    no_match_count: Optional[int] = None
    unmatched_queries: Optional[List[str]] = None


def create_app(
    *,
    settings: Optional[WorkerSettings] = None,
    job_store: Optional[JobStore] = None,
    rate_limiter: Optional[RateLimiter] = None,
    model_registry: Optional[ModelRegistry] = None,
    catalog_client: Optional[BaseCatalogClient] = None,
) -> FastAPI:
    """
    Build the worker FastAPI app.

    Tests inject store / limiter / registry / catalog as needed.
    """
    configure_logging()
    worker_settings = settings or WorkerSettings.from_env()
    store = job_store or InMemoryJobStore(ttl_s=worker_settings.job_ttl_s)
    limiter = rate_limiter or RateLimiter()
    backend = "sample" if worker_settings.use_sample_catalog else "sentence-transformers"
    registry = model_registry or ModelRegistry(backend=backend)

    client = catalog_client
    if client is None and worker_settings.use_sample_catalog:
        client = SampleCatalogClient(worker_settings.sample_catalog_path)

    orch = JobOrchestrator(
        store,
        embedder_provider=registry.get,
        catalog_client=client,
        use_sample_catalog=worker_settings.use_sample_catalog,
        sample_catalog_path=worker_settings.sample_catalog_path,
        job_timeout_s=worker_settings.job_timeout_s,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        """
        Preload the embedder on startup when not skipped; failures fall back to
        lazy-load on warmup/job.
        """
        if not worker_settings.skip_model_preload:
            try:
                registry.preload()
                log.info("embedder preloaded backend=%s", registry.backend)
            except Exception:
                log.exception("embedder preload failed; will lazy-load on warmup/job")
        yield

    app = FastAPI(title="supermarket-linkage-worker", lifespan=lifespan)
    app.state.settings = worker_settings
    app.state.job_store = store
    app.state.rate_limiter = limiter
    app.state.model_registry = registry
    app.state.orchestrator = orch

    def require_api_key(request: Request) -> None:
        """Require API key when configured; raise 401 if missing or wrong."""
        expected = request.app.state.settings.api_key
        if not expected:
            return
        provided = None
        for name in API_KEY_HEADERS:
            provided = request.headers.get(name)
            if provided:
                break
        if provided is None or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    def client_ip(request: Request) -> str:
        """
        Return the direct peer IP. Do not trust X-Forwarded-For (spoof bypass).
        """
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    @app.get("/health")
    def health(request: Request) -> Dict[str, Any]:
        """
        Liveness probe: process is up. ``status`` is always ok when reachable;
        readiness for matching is ``warm``.
        """
        reg: ModelRegistry = request.app.state.model_registry
        st: WorkerSettings = request.app.state.settings
        return {
            "status": "ok",
            "warm": reg.warm,
            "use_sample_catalog": st.use_sample_catalog,
        }

    @app.post("/warmup", dependencies=[Depends(require_api_key)])
    def warmup(request: Request) -> Dict[str, Any]:
        """Preload the embedding model; rate-limited per IP."""
        ip = client_ip(request)
        limiter_inst: RateLimiter = request.app.state.rate_limiter
        if not limiter_inst.allow_warmup(ip):
            raise HTTPException(status_code=429, detail="Warmup rate limit exceeded")
        reg: ModelRegistry = request.app.state.model_registry
        try:
            reg.preload()
        except Exception:
            log.exception("warmup failed")
            raise HTTPException(status_code=500, detail="Warmup failed") from None
        return {"status": "ok", "warm": True, "backend": reg.backend}

    @app.post("/jobs", status_code=202, dependencies=[Depends(require_api_key)])
    def create_job(
        body: JobCreateBody,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> JobCreateResponse:
        """
        Validate input, enqueue a linkage job, and return its id for polling.
        Does not log ``body.text``.
        """
        orch_inst: JobOrchestrator = request.app.state.orchestrator
        limiter_inst: RateLimiter = request.app.state.rate_limiter
        store_inst: JobStore = request.app.state.job_store
        ip = client_ip(request)

        try:
            store_id = assert_supported_store(body.store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

        postal = (body.postal_code or "").strip() or None
        if postal is not None and not is_valid_postal_code(postal):
            raise HTTPException(status_code=400, detail="Invalid postal code.")

        validated = orch_inst.validate_text(body.text)
        if not validated.ok:
            raise HTTPException(status_code=400, detail=validated.error or "Invalid input.")

        if not limiter_inst.consume_job(ip):
            raise HTTPException(status_code=429, detail="Job rate limit exceeded")

        job_id = uuid.uuid4().hex
        n = len(validated.lines)
        record = JobRecord(
            id=job_id,
            status=STATUS_QUEUED,
            progress=JobProgress(done=0, total=n, status=STATUS_QUEUED),
            warnings=list(validated.warnings),
        )
        spec = JobSpec(
            lines=tuple(validated.lines),
            store=store_id,
            postal_code=postal,
            is_promo_member=body.is_promo_member,
            warnings=tuple(validated.warnings),
        )

        def _run_job() -> None:
            try:
                orch_inst.run(job_id, spec)
            finally:
                limiter_inst.release_job(ip)

        try:
            store_inst.create(record)
            background_tasks.add_task(_run_job)
        except Exception:
            limiter_inst.release_job(ip)
            raise

        return JobCreateResponse(
            id=job_id,
            status=STATUS_QUEUED,
            progress=ProgressBody(done=0, total=n, status=STATUS_QUEUED),
            warnings=list(validated.warnings),
        )

    @app.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
    def get_job(job_id: str, request: Request) -> JobGetResponse:
        """Return job progress, results (including no_match rows), and summary counts."""
        store_inst: JobStore = request.app.state.job_store
        job = store_inst.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobGetResponse(
            id=job.id,
            status=job.status,
            progress=ProgressBody(
                done=job.progress.done,
                total=job.progress.total,
                status=job.progress.status,
            ),
            warnings=job.warnings,
            results=job.results,
            error=job.error,
            matched_count=job.matched_count,
            no_match_count=job.no_match_count,
            unmatched_queries=job.unmatched_queries,
        )

    return app


app = create_app()
