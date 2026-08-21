"""Unit tests for job result summary helpers."""

from supermarket_linkage.pipeline.consts import STATUS_MATCHED, STATUS_NO_MATCH
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.worker.job_orchestrator import _split_hits, summarize_results
import polars as pl


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
