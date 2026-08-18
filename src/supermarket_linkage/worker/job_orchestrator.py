"""Run one job: validate → dedupe → search_batch → linkage, with progress.

Never log the full paste (Decision 14). Time out after ``JOB_TIMEOUT_SECONDS``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import polars as pl

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.catalog.catalog_client_factory import CatalogClientFactory
from supermarket_linkage.catalog.promo_policy import MercadonaPromoPolicy, PromoPolicy
from supermarket_linkage.consts import JOB_TIMEOUT_SECONDS, SUPPORTED_STORES
from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator
from supermarket_linkage.pipeline.semantic_stage import Embedder
from supermarket_linkage.preprocessors.text_normalizer import extract_search_query
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.validation.input_validator import InputValidator, ValidationResult
from supermarket_linkage.worker.job_store import (
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_LINKING,
    STATUS_RUNNING,
    STATUS_SEARCHING,
    STATUS_TIMEOUT,
    JobProgress,
    JobStore,
)
from supermarket_linkage.worker.sample_catalog import SampleCatalogClient

log = logging.getLogger(__name__)


class JobTimeoutError(Exception):
    """Job exceeded ``JOB_TIMEOUT_SECONDS``."""


@dataclass(frozen=True)
class JobSpec:
    """Validated job payload. ``lines`` only — not the raw paste."""

    lines: tuple[str, ...]
    store: str
    postal_code: str | None
    is_promo_member: bool
    warnings: tuple[str, ...] = ()


class JobOrchestrator:
    """Drive catalog fetch + linkage and write progress to ``JobStore``."""

    def __init__(
        self,
        job_store: JobStore,
        *,
        embedder_provider: Callable[[], Embedder],
        catalog_client: BaseCatalogClient | None = None,
        use_sample_catalog: bool = False,
        sample_catalog_path: str | None = None,
        job_timeout_s: int = JOB_TIMEOUT_SECONDS,
        promo_policy: PromoPolicy | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._store = job_store
        self._embedder_provider = embedder_provider
        self._fixed_client = catalog_client
        self._use_sample = use_sample_catalog
        self._sample_path = sample_catalog_path
        self._sample_client: SampleCatalogClient | None = None
        self._live_clients: dict[str, BaseCatalogClient] = {}
        self._timeout_s = job_timeout_s
        self._promo = promo_policy or MercadonaPromoPolicy()
        self._now = now or time.monotonic
        self._validator = InputValidator()

    def validate_text(self, text: str) -> ValidationResult:
        """Sanitize paste. Callers must not log ``text``."""
        return self._validator.validate(text)

    def run(self, job_id: str, spec: JobSpec) -> None:
        """Execute ``spec``. Caller releases the rate-limit slot.

        Pre: ``spec.lines`` already passed ``InputValidator``.
        Post: job is ``done``, ``error``, or ``timeout``. Paste is not stored.
        """
        n = len(spec.lines)
        deadline = self._now() + self._timeout_s
        try:
            self._store.update(
                job_id,
                status=STATUS_RUNNING,
                progress=JobProgress(done=0, total=n, status=STATUS_SEARCHING),
            )
            log.info("job %s start line_count=%s store=%s", job_id, n, spec.store)
            results = self._execute(job_id, spec, deadline=deadline)
            self._store.update(
                job_id,
                status=STATUS_DONE,
                progress=JobProgress(done=n, total=n, status=STATUS_DONE),
                results=results,
            )
            log.info("job %s done line_count=%s", job_id, n)
        except JobTimeoutError:
            log.warning("job %s timeout after %ss", job_id, self._timeout_s)
            self._store.update(
                job_id,
                status=STATUS_TIMEOUT,
                progress=JobProgress(done=0, total=n, status=STATUS_TIMEOUT),
                error=f"Job exceeded {self._timeout_s}s.",
            )
        except Exception:
            # Do not include paste or line text in the log message.
            log.exception("job %s failed store=%s line_count=%s", job_id, spec.store, n)
            self._store.update(
                job_id,
                status=STATUS_ERROR,
                progress=JobProgress(done=0, total=n, status=STATUS_ERROR),
                error="Job failed.",
            )

    def _execute(
        self,
        job_id: str,
        spec: JobSpec,
        *,
        deadline: float,
    ) -> list[dict[str, object]]:
        self._check_deadline(deadline)
        query_norms = [extract_search_query(line) for line in spec.lines]
        unique = list(dict.fromkeys(q for q in query_norms if q))

        client = self._client_for(spec.store)
        hits = client.search_batch(unique, postal_code=spec.postal_code)
        by_query = _split_hits(hits, unique)

        self._check_deadline(deadline)
        self._store.update(
            job_id,
            status=STATUS_RUNNING,
            progress=JobProgress(done=0, total=len(spec.lines), status=STATUS_LINKING),
        )

        embedder = self._embedder_provider()
        linkage = LinkageOrchestrator(embedder=embedder, store=spec.store)
        frames: list[pl.DataFrame] = []
        for i, (line, q_norm) in enumerate(zip(spec.lines, query_norms, strict=True)):
            self._check_deadline(deadline)
            products = by_query.get(q_norm)
            if products is None:
                products = ProductTable.as_empty_dataframe()
            result = linkage.link_line(
                line,
                products,
                line_index=i,
                query_norm=q_norm,
            )
            result = _apply_promo(result, spec.is_promo_member, self._promo)
            frames.append(result)
            self._store.update(
                job_id,
                status=STATUS_RUNNING,
                progress=JobProgress(
                    done=i + 1,
                    total=len(spec.lines),
                    status=STATUS_LINKING,
                ),
            )

        if not frames:
            return []
        out = LineResultTable.enforce_schema(pl.concat(frames, how="diagonal_relaxed"))
        return out.to_dicts()

    def _client_for(self, store: str) -> BaseCatalogClient:
        if self._fixed_client is not None:
            return self._fixed_client
        if self._use_sample:
            if self._sample_client is None:
                self._sample_client = SampleCatalogClient(self._sample_path)
            return self._sample_client
        cached = self._live_clients.get(store)
        if cached is not None:
            return cached
        client = CatalogClientFactory.get(store)
        self._live_clients[store] = client
        return client

    def _check_deadline(self, deadline: float) -> None:
        if self._now() >= deadline:
            raise JobTimeoutError()


def assert_supported_store(store: str) -> str:
    """Normalize store id or raise ``ValueError``."""
    key = store.strip().lower()
    if key not in SUPPORTED_STORES:
        raise ValueError(f"Store {store!r} is not available in v1.")
    return key


def _split_hits(hits: pl.DataFrame, unique: Sequence[str]) -> dict[str, pl.DataFrame]:
    if hits.height == 0:
        return {q: ProductTable.as_empty_dataframe() for q in unique}
    out: dict[str, pl.DataFrame] = {}
    src = ProductColumns.SOURCE_QUERY
    for q in unique:
        part = hits.filter(pl.col(src) == q)
        out[q] = (
            ProductTable.enforce_schema(part)
            if part.height
            else ProductTable.as_empty_dataframe()
        )
    return out


def _apply_promo(
    result: pl.DataFrame,
    is_promo_member: bool,
    policy: PromoPolicy,
) -> pl.DataFrame:
    """Set effective pack price and line total from ``PromoPolicy``."""
    effective: list[float | None] = []
    totals: list[float | None] = []
    for row in result.iter_rows(named=True):
        price = policy.effective_price(row, is_promo_member)
        units = row.get(LineResultColumns.UNITS_NEEDED)
        total = (float(units) * price) if price is not None and units is not None else None
        effective.append(price)
        totals.append(total)
    out = result.with_columns(
        [
            pl.Series(LineResultColumns.EFFECTIVE_PRICE_EUR, effective, dtype=pl.Float64),
            pl.Series(LineResultColumns.LINE_TOTAL_PRICE_EUR, totals, dtype=pl.Float64),
        ]
    )
    return LineResultTable.enforce_schema(out)
