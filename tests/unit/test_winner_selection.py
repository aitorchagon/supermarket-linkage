"""Unit tests for Branch A / Branch B winner selection."""

import polars as pl

from supermarket_linkage.pipeline.linkage_orchestrator import select_winner
from supermarket_linkage.schemas.candidate_table import CandidateColumns


def _survivors(**cols: list) -> pl.DataFrame:
    return pl.DataFrame(cols)


def test_branch_a_lowest_price_per_kg() -> None:
    df = _survivors(
        product_id=["cheap", "pricey"],
        price_per_kg=[1.0, 2.0],
        jw_similarity=[0.91, 0.99],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "cheap"


def test_branch_a_jw_tiebreak() -> None:
    df = _survivors(
        product_id=["low_jw", "high_jw"],
        price_per_kg=[1.5, 1.5],
        jw_similarity=[0.92, 0.98],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "high_jw"


def test_branch_a_priced_beats_null() -> None:
    df = _survivors(
        product_id=["priced", "null_price"],
        price_per_kg=[3.0, None],
        jw_similarity=[0.91, 0.99],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "priced"


def test_branch_b_all_null_highest_jw() -> None:
    df = _survivors(
        product_id=["a", "b"],
        price_per_kg=[None, None],
        jw_similarity=[0.91, 0.97],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "b"


def test_select_winner_empty() -> None:
    empty = pl.DataFrame(
        schema={
            CandidateColumns.PRODUCT_ID: pl.String,
            CandidateColumns.PRICE_PER_KG: pl.Float64,
            CandidateColumns.JW_SIMILARITY: pl.Float64,
        }
    )
    assert select_winner(empty).height == 0
