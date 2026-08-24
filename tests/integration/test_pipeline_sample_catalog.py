from __future__ import annotations

import json
from typing import (
    List,
    Dict,
)
from pathlib import Path
import pytest

import polars as pl
import numpy as np

from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator
from supermarket_linkage.preprocessors.price_normalizer import PriceNormalizer
from supermarket_linkage.preprocessors.text_normalizer import extract_search_query, normalize_text
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_catalog.json"

_SKIP = frozenset({"kg", "g", "l", "ml", "cl", "uds", "ud", "x", "pack", "packs"})

class _TokenOverlapEmbedder:
    """Deterministic bag-of-content-tokens (CI-safe, no downloads)."""

    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}

    def _tokens(self, text: str) -> List[str]:
        return [t for t in (text or "").lower().split() if t.isalpha() and t not in _SKIP]

    def embed(self, texts: List[str]):
    
        for text in texts:
            for tok in self._tokens(text):
                if tok not in self._vocab:
                    self._vocab[tok] = len(self._vocab)
        dim = max(len(self._vocab), 1)
        out = np.zeros((len(texts), dim), dtype=np.float64)
        for i, text in enumerate(texts):
            for tok in self._tokens(text):
                out[i, self._vocab[tok]] = 1.0
        return out


def _load_catalog() -> pl.DataFrame:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    df = pl.DataFrame(raw)
    df = ProductTable.enforce_schema(df)
    return PriceNormalizer().process(df)


def _search_offline(catalog: pl.DataFrame, query_norm: str) -> pl.DataFrame:
    """Return products whose name tokens contain all query tokens; tag source_query."""
    q_tokens = query_norm.split()
    if not q_tokens:
        return ProductTable.as_empty_dataframe()

    rows = []
    for row in catalog.iter_rows(named=True):
        name_norm = normalize_text(row[ProductColumns.NAME] or "")
        name_tokens = set(name_norm.split())
        if all(t in name_tokens for t in q_tokens):
            rows.append(row)

    if not rows:
        return ProductTable.as_empty_dataframe()

    hits = pl.DataFrame(rows)
    hits = hits.with_columns(
        pl.lit(query_norm).alias(ProductColumns.SOURCE_QUERY)
    )
    return ProductTable.enforce_schema(hits)


@pytest.fixture(scope="module")
def catalog() -> pl.DataFrame:
    return _load_catalog()


@pytest.fixture
def orchestrator() -> LinkageOrchestrator:
    return LinkageOrchestrator(embedder=_TokenOverlapEmbedder(), store="mercadona")


def test_sample_catalog_size(catalog: pl.DataFrame) -> None:
    assert 30 <= catalog.height <= 50


def test_pipeline_arroz_basmati_picks_cheaper_per_kg(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "arroz basmati 1500 g"
    q_norm = extract_search_query(query)
    products = _search_offline(catalog, q_norm)
    assert products.height >= 2

    result = orchestrator.link_line(query, products, line_index=0)
    assert result[LineResultColumns.STATUS][0] == "matched"
    # 500 g pack is 1.90 €/kg vs 1 kg at 1.50 €/kg → 1 kg wins Branch A.
    assert result[LineResultColumns.PRODUCT_ID][0] == "4245"
    assert result[LineResultColumns.UNITS_NEEDED][0] == 2
    assert result[LineResultColumns.PACK_SIZE_MISSING][0] is False


def test_pipeline_leche_entera(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "leche entera 1l"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=1)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "30902"
    assert result[LineResultColumns.UNITS_NEEDED][0] == 1


def test_pipeline_branch_b_unidad_no_weight(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "huevos camperos"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=2)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "8001"
    assert result[LineResultColumns.PRICE_PER_KG][0] is None
    assert result[LineResultColumns.UNITS_NEEDED][0] == 1


def test_pipeline_no_match(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "salsa de soja premium inexistente"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=3)
    assert result[LineResultColumns.STATUS][0] == "no_match"
    assert result[LineResultColumns.PRODUCT_ID][0] is None


def test_pipeline_link_lines_batch(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    lines = pl.DataFrame(
        {
            "query": ["arroz basmati 1 kg", "aceite de oliva virgen extra 1l", "xyzzy no product"],
        }
    )
    by_q: dict[str, pl.DataFrame] = {}
    for q in lines["query"].to_list():
        qn = extract_search_query(q)
        by_q[qn] = _search_offline(catalog, qn)

    out = orchestrator.link_lines(lines, by_q)
    assert out.height == 3
    assert out[LineResultColumns.STATUS].to_list()[0] == "matched"
    assert out[LineResultColumns.STATUS].to_list()[1] == "matched"
    assert out[LineResultColumns.STATUS].to_list()[2] == "no_match"
