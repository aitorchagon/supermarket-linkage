"""Unit tests for job result summary helpers."""

import numpy as np
import polars as pl

from supermarket_linkage.pipeline.consts import STATUS_MATCHED, STATUS_NO_MATCH
from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.worker.job_orchestrator import (
    _link_line_with_alternatives,
    _split_hits,
    summarize_results,
)


def test_summarize_results_counts_and_queries() -> None:
    rows = [
        {
            LineResultColumns.STATUS: STATUS_MATCHED,
            LineResultColumns.QUERY: "arroz",
        },
        {
            LineResultColumns.STATUS: STATUS_NO_MATCH,
            LineResultColumns.QUERY: "xyz",
        },
        {
            LineResultColumns.STATUS: STATUS_NO_MATCH,
            LineResultColumns.QUERY: "abc",
        },
    ]
    summary = summarize_results(rows)
    assert summary.matched_count == 1
    assert summary.no_match_count == 2
    assert summary.unmatched_queries == ("xyz", "abc")


def test_split_hits_partition_by_source_query() -> None:
    hits = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["1", "2", "3"],
            ProductColumns.NAME: ["a", "b", "c"],
            ProductColumns.BRAND: [None, None, None],
            ProductColumns.PRICE_EUR: [1.0, 2.0, 3.0],
            ProductColumns.PROMO_PRICE_EUR: [None, None, None],
            ProductColumns.UNIT_PRICE_EUR: [None, None, None],
            ProductColumns.UNIT_MEASURE: [None, None, None],
            ProductColumns.APPROX_WEIGHT_KG: [None, None, None],
            ProductColumns.PRICE_PER_KG: [None, None, None],
            ProductColumns.SOURCE_QUERY: ["leche", "arroz", "leche"],
            ProductColumns.URL: [None, None, None],
        }
    )
    parts = _split_hits(hits, unique=["leche", "arroz", "nada"])
    assert parts["leche"].height == 2
    assert parts["arroz"].height == 1
    assert parts["nada"].height == 0
    assert parts["nada"].columns == ProductTable.columns()


class _TokenEmbedder:
    def embed(self, texts):
        dim = max(len(texts), 1)
        return np.eye(dim, dtype=np.float64)[: len(texts)]


def test_link_line_with_alternatives_tries_second_branch() -> None:
    """First OR branch empty hits; second branch matches."""
    linkage = LinkageOrchestrator(embedder=_TokenEmbedder(), store="mercadona")
    empty = ProductTable.as_empty_dataframe()
    leche = ProductTable.enforce_schema(
        pl.DataFrame(
            {
                ProductColumns.PRODUCT_ID: ["30902"],
                ProductColumns.NAME: ["Leche entera 1 l"],
                ProductColumns.BRAND: ["Hacendado"],
                ProductColumns.PRICE_EUR: [0.84],
                ProductColumns.PROMO_PRICE_EUR: [None],
                ProductColumns.UNIT_PRICE_EUR: [0.84],
                ProductColumns.UNIT_MEASURE: ["LITRO"],
                ProductColumns.APPROX_WEIGHT_KG: [1.0],
                ProductColumns.PRICE_PER_KG: [0.84],
                ProductColumns.SOURCE_QUERY: ["leche"],
                ProductColumns.URL: [None],
            }
        )
    )
    result = _link_line_with_alternatives(
        linkage=linkage,
        line="bebida vegetal o leche 6l",
        alternatives=["bebida vegetal", "leche"],
        hits_by_query={"bebida vegetal": empty, "leche": leche},
        line_index=0,
    )
    assert result[LineResultColumns.STATUS][0] == STATUS_MATCHED
    assert result[LineResultColumns.PRODUCT_ID][0] == "30902"
