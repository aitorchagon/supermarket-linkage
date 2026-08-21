"Offline catalog client for testing"

from __future__ import annotations

from typing import (
    List,
    Set,
    Optional,
    Union,
)
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
    """
    This function allows to resolve a fixture path from env, then goes to tests/fixtures.
    """
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


def load_sample_catalog(path: Optional[Path] = None) -> pl.DataFrame:
    """
    This function loads Mercadona-shaped products and fill price per kg."""
    target = path or default_sample_catalog_path()
    raw = json.loads(target.read_text(encoding="utf-8"))
    df = ProductTable.enforce_schema(pl.DataFrame(raw))
    return PriceNormalizer().process(df)


class SampleCatalogClient(BaseCatalogClient):
    """
    This client allows for a token-subset search over a static JSON catalog.
    """

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        resolved = Path(path) if path else None
        self._catalog = load_sample_catalog(resolved)
        self._name_tokens: List[Set[str]] = [
            set(normalize_text(name or "").split())
            for name in self._catalog[ProductColumns.NAME].to_list()
        ]

    def search(self, query: str, *, postal_code: Optional[str] = None) -> pl.DataFrame:
        """
        We delete the postal code and perform a search over the batch.
        """
        del postal_code
        return self.search_products([query])

    def search_products(
        self,
        queries: Sequence[str],
        *,
        postal_code: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        This function allows to match products whose name tokens contain all query tokens.
        The queries are search strings (raw or already normalized); the function returns ProductTable
        rows.
        """
        del postal_code
        frames: List[pl.DataFrame] = []
        for raw in queries:
            if not raw or not str(raw).strip():
                continue
            q_norm = extract_search_query(str(raw))
            frames.append(self._search_product(q_norm))
        if not frames:
            return ProductTable.as_empty_dataframe()
        return ProductTable.enforce_schema(pl.concat(frames, how="diagonal"))

    def _search_product(self, query_norm: str) -> pl.DataFrame:
        """
        This function allows to match a prodyc whose name tokens contain all query tokens.
        The queries are search strings (raw or already normalized); the function returns ProductTable
        rows.
        """
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