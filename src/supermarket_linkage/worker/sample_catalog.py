"""Offline catalog client for ``USE_SAMPLE_CATALOG=1`` (no Mercadona HTTP)."""

from __future__ import annotations

import json
import os
from typing import Sequence
from pathlib import Path

import polars as pl

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.preprocessors.price_normalizer import PriceNormalizer
from supermarket_linkage.preprocessors.text_normalizer import extract_search_query, normalize_text
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable


def default_sample_catalog_path() -> Path:
    """Resolve fixture path from env, then repo ``tests/fixtures``."""
    env = os.environ.get("SAMPLE_CATALOG_PATH", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    repo = here.parents[3]
    candidates = (
        repo / "tests" / "fixtures" / "sample_catalog.json",
        repo / "data" / "sample_catalog.json",
        Path.cwd() / "tests" / "fixtures" / "sample_catalog.json",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "sample_catalog.json not found. Set SAMPLE_CATALOG_PATH or run from the repo."
    )


def load_sample_catalog(path: Path | None = None) -> pl.DataFrame:
    """Load Mercadona-shaped products and fill price/kg."""
    target = path or default_sample_catalog_path()
    raw = json.loads(target.read_text(encoding="utf-8"))
    df = ProductTable.enforce_schema(pl.DataFrame(raw))
    return PriceNormalizer().process(df)


class SampleCatalogClient(BaseCatalogClient):
    """Token-subset search over a static catalog JSON."""

    def __init__(self, path: str | Path | None = None) -> None:
        resolved = Path(path) if path else None
        self._catalog = load_sample_catalog(resolved)
        self._name_tokens: List[Set[str]] = [
            set(normalize_text(name or "").split())
            for name in self._catalog[ProductColumns.NAME].to_list()
        ]

    def search(self, query: str, *, postal_code: str | None = None) -> pl.DataFrame:
        del postal_code
        return self.search_batch([query])

    def search_batch(
        self,
        queries: Sequence[str],
        *,
        postal_code: str | None = None,
    ) -> pl.DataFrame:
        """Match products whose name tokens contain all query tokens.

        Pre: ``queries`` are search strings (raw or already normalized).
        Post: ProductTable rows; ``source_query`` is ``extract_search_query(q)``.
        """
        del postal_code
        frames: List[pl.DataFrame] = []
        for raw in queries:
            if not raw or not str(raw).strip():
                continue
            q_norm = extract_search_query(str(raw))
            frames.append(self._search_one(q_norm))
        if not frames:
            return ProductTable.as_empty_dataframe()
        return ProductTable.enforce_schema(pl.concat(frames, how="diagonal"))

    def _search_one(self, query_norm: str) -> pl.DataFrame:
        tokens = [t for t in query_norm.split() if t]
        if not tokens:
            return ProductTable.as_empty_dataframe()
        rows = [
            self._catalog.row(i, named=True)
            for i, name_tokens in enumerate(self._name_tokens)
            if all(t in name_tokens for t in tokens)
        ]
        if not rows:
            empty = ProductTable.as_empty_dataframe()
            return empty
        hits = pl.DataFrame(rows).with_columns(
            pl.lit(query_norm).alias(ProductColumns.SOURCE_QUERY)
        )
        return ProductTable.enforce_schema(hits)
