from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)

import polars as pl

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.catalog.catalog_client_factory import CatalogClientFactory
from supermarket_linkage.catalog.promo_policy import MercadonaPromoPolicy, PromoPolicy
from supermarket_linkage.consts import JOB_TIMEOUT_SECONDS, SUPPORTED_STORES
from supermarket_linkage.pipeline.consts import STATUS_MATCHED, STATUS_NO_MATCH
from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator
from supermarket_linkage.pipeline.semantic_stage import Embedder
from supermarket_linkage.preprocessors.text_normalizer import extract_search_query
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.validation.input_validator import InputValidator, ValidationResult
from supermarket_linkage.worker.consts import (
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_LINKING,
    STATUS_RUNNING,
    STATUS_SEARCHING,
    STATUS_TIMEOUT,
)
from supermarket_linkage.worker.job_store import JobProgress, JobStore
from supermarket_linkage.worker.sample_catalog import SampleCatalogClient

log = logging.getLogger(__name__)


class JobTimeoutError(Exception):
    """Job exceeded ``job_timeout`` seconds."""


@dataclass(frozen=True)
class JobSpec:
    """Validated job payload (lines already sanitized; paste not retained)."""

    lines: Tuple[str, ...]
    store: str
    postal_code: Optional[str]
    is_promo_member: bool
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultsSummary:
    """Counts and queries for matched vs unmatched lines."""

    matched_count: int
    no_match_count: int
    unmatched_queries: Tuple[str, ...]


class JobOrchestrator:
    """
    Drive catalog fetch and record linkage while writing progress to JobStore.
    """

    def __init__(
        self,
        job_store: JobStore,
        *,
        embedder_provider: Callable[[], Embedder],
        catalog_client: Optional[BaseCatalogClient] = None,
        use_sample_catalog: bool = False,
        sample_catalog_path: Optional[str] = None,
        job_timeout_s: int = JOB_TIMEOUT_SECONDS,
        promo_policy: Optional[PromoPolicy] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._store = job_store
        self._embedder_provider = embedder_provider
        self._fixed_client = catalog_client
        self._use_sample = use_sample_catalog
        self._sample_path = sample_catalog_path
        self._sample_client: Optional[SampleCatalogClient] = None
        self._live_clients: Dict[str, BaseCatalogClient] = {}
        self._timeout_s = job_timeout_s
        self._promo = promo_policy or MercadonaPromoPolicy()
        self._now = now or time.monotonic
        self._validator = InputValidator()

    def validate_text(self, text: str) -> ValidationResult:
        """Sanitize pasted text (limits, control chars); do not log the paste."""
        return self._validator.validate(text)

    def run(self, job_id: str, spec: JobSpec) -> None:
        """
        Execute ``spec`` and update the store. Caller releases the rate-limit slot.
        Status ends as done, error, or timeout. Pasted text is not stored.
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
            summary = summarize_results(results)
            self._store.update(
                job_id,
                status=STATUS_DONE,
                progress=JobProgress(done=n, total=n, status=STATUS_DONE),
                results=results,
                matched_count=summary.matched_count,
                no_match_count=summary.no_match_count,
                unmatched_queries=list(summary.unmatched_queries),
            )
            log.info(
                "job %s done line_count=%s matched=%s no_match=%s",
                job_id,
                n,
                summary.matched_count,
                summary.no_match_count,
            )
        except JobTimeoutError:
            log.warning("job %s timeout after %ss", job_id, self._timeout_s)
            self._store.update(
                job_id,
                status=STATUS_TIMEOUT,
                progress=JobProgress(done=0, total=n, status=STATUS_TIMEOUT),
                error=f"Job exceeded {self._timeout_s}s.",
            )
        except Exception:
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
    ) -> List[Dict[str, object]]:
        self._check_deadline(deadline)
        query_norms = [extract_search_query(line) for line in spec.lines]
        unique = list(dict.fromkeys(q for q in query_norms if q))

        client = self._create_client(spec.store)
        hits = client.search_batch(
            queries=unique,
            postal_code=spec.postal_code,
        )
        hits_by_query = _split_hits(hits=hits, unique=unique)

        self._check_deadline(deadline=deadline)
        self._store.update(
            job_id=job_id,
            status=STATUS_RUNNING,
            progress=JobProgress(done=0, total=len(spec.lines), status=STATUS_LINKING),
        )

        embedder = self._embedder_provider()
        linkage = LinkageOrchestrator(embedder=embedder, store=spec.store)
        frames: List[pl.DataFrame] = []
        for i, (line, normalized_query) in enumerate(zip(spec.lines, query_norms, strict=True)):
            self._check_deadline(deadline)
            products = hits_by_query.get(normalized_query)
            if products is None:
                products = ProductTable.as_empty_dataframe()
            result = linkage.link_line(
                query=line,
                products=products,
                line_index=i,
                query_norm=normalized_query,
            )
            result = _apply_promo(
                result=result,
                is_promo_member=spec.is_promo_member,
                policy=self._promo,
            )
            frames.append(result)
            self._store.update(
                job_id=job_id,
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

    def _create_client(self, store: str) -> BaseCatalogClient:
        """
        Resolve the catalog client: fixed (tests), sample, cached live, or factory.
        """
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
    """Normalize store id; raise ValueError if not available in v1."""
    key = store.strip().lower()
    if key not in SUPPORTED_STORES:
        raise ValueError(f"Store {store!r} is not available in v1.")
    return key


def summarize_results(results: Sequence[Dict[str, object]]) -> ResultsSummary:
    """Count matched / no_match rows and collect unmatched query strings."""
    matched = 0
    unmatched: List[str] = []
    for row in results:
        status = str(row.get(LineResultColumns.STATUS) or "")
        if status == STATUS_MATCHED:
            matched += 1
        elif status == STATUS_NO_MATCH:
            unmatched.append(str(row.get(LineResultColumns.QUERY) or "").strip())
    return ResultsSummary(
        matched_count=matched,
        no_match_count=len(unmatched),
        unmatched_queries=tuple(unmatched),
    )


def _split_hits(hits: pl.DataFrame, unique: Sequence[str]) -> Dict[str, pl.DataFrame]:
    """
    Partition batch search hits by ``source_query`` into one frame per unique query.

    Uses ``partition_by(..., as_dict=True)`` instead of one filter scan per query.
    """
    empty = ProductTable.as_empty_dataframe()
    if hits.height == 0:
        return {q: empty for q in unique}

    src = ProductColumns.SOURCE_QUERY
    parts = hits.partition_by(src, as_dict=True, include_key=True)
    # Polars may key single-column partitions by scalar or 1-tuple depending on version.
    by_query: Dict[str, pl.DataFrame] = {}
    for key, frame in parts.items():
        if isinstance(key, tuple):
            q = key[0] if len(key) == 1 else key
        else:
            q = key
        by_query[str(q)] = ProductTable.enforce_schema(frame)

    return {q: by_query.get(q, empty) for q in unique}


def _apply_promo(
    result: pl.DataFrame,
    is_promo_member: bool,
    policy: PromoPolicy,
) -> pl.DataFrame:
    """Set effective pack price and line total from PromoPolicy (usually one row)."""
    effective: List[Optional[float]] = []
    totals: List[Optional[float]] = []
    for row in result.iter_rows(named=True):
        price = policy.effective_price(row, is_promo_member)
        units = row.get(LineResultColumns.UNITS_NEEDED)
        total = (
            (float(units) * price) if price is not None and units is not None else None
        )
        effective.append(price)
        totals.append(total)
    out = result.with_columns(
        [
            pl.Series(LineResultColumns.EFFECTIVE_PRICE_EUR, effective, dtype=pl.Float64),
            pl.Series(LineResultColumns.LINE_TOTAL_PRICE_EUR, totals, dtype=pl.Float64),
        ]
    )
    return LineResultTable.enforce_schema(out)
