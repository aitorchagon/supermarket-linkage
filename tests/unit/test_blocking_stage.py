import polars as pl

from supermarket_linkage.pipeline.blocking_stage import BlockingStage
from supermarket_linkage.schemas.candidate_table import CandidateColumns


def test_blocking_keeps_same_source_query() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1", "2", "3"],
            CandidateColumns.NAME: ["A", "B", "C"],
            CandidateColumns.SOURCE_QUERY: ["arroz basmati", "leche", "arroz basmati"],
            CandidateColumns.QUERY_NORM: ["arroz basmati"] * 3,
        }
    )
    out = BlockingStage().process(df)
    assert out[CandidateColumns.PRODUCT_ID].to_list() == ["1", "3"]


def test_blocking_drops_all_when_no_match() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1"],
            CandidateColumns.NAME: ["X"],
            CandidateColumns.SOURCE_QUERY: ["other"],
            CandidateColumns.QUERY_NORM: ["arroz"],
        }
    )
    out = BlockingStage().process(df)
    assert out.height == 0


def test_blocking_empty() -> None:
    assert BlockingStage().process(pl.DataFrame()).height == 0
