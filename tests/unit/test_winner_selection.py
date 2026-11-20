import numpy as np
import polars as pl
import pytest

from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator, select_winner
from supermarket_linkage.schemas.candidate_table import CandidateColumns
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable


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


def test_branch_a_semantic_score_tiebreak() -> None:
    df = _survivors(
        product_id=["low_sem", "high_sem"],
        price_per_kg=[1.5, 1.5],
        jw_similarity=[0.95, 0.95],
        semantic_score=[0.78, 0.94],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "high_sem"


def test_branch_b_semantic_score_tiebreak() -> None:
    df = _survivors(
        product_id=["low_sem", "high_sem"],
        price_per_kg=[None, None],
        jw_similarity=[0.95, 0.95],
        semantic_score=[0.76, 0.91],
    )
    winner = select_winner(df)
    assert winner[CandidateColumns.PRODUCT_ID][0] == "high_sem"


def test_select_winner_empty() -> None:
    empty = pl.DataFrame(
        schema={
            CandidateColumns.PRODUCT_ID: pl.String,
            CandidateColumns.PRICE_PER_KG: pl.Float64,
            CandidateColumns.JW_SIMILARITY: pl.Float64,
        }
    )
    assert select_winner(empty).height == 0


class _ConstEmbedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 1), dtype=np.float64)


def test_promo_member_flips_winner_in_orchestrator() -> None:
    products = ProductTable.enforce_schema(
        pl.DataFrame(
            {
                ProductColumns.PRODUCT_ID: ["reg_cheaper", "promo_cheaper"],
                ProductColumns.NAME: ["Arroz basmati marca A 1 kg", "Arroz basmati marca B 1 kg"],
                ProductColumns.PRICE_EUR: [1.50, 1.60],
                ProductColumns.PROMO_PRICE_EUR: [None, 1.20],
                ProductColumns.UNIT_PRICE_EUR: [1.50, 1.20],
                ProductColumns.UNIT_MEASURE: ["KILO", "KILO"],
                ProductColumns.APPROX_WEIGHT_KG: [1.0, 1.0],
                ProductColumns.SOURCE_QUERY: ["arroz basmati", "arroz basmati"],
            }
        )
    )
    orchestrator = LinkageOrchestrator(embedder=_ConstEmbedder())

    regular_res = orchestrator.link_line("arroz basmati 1 kg", products, is_promo_member=False)
    assert regular_res[LineResultColumns.PRODUCT_ID][0] == "reg_cheaper"
    assert regular_res[LineResultColumns.EFFECTIVE_PRICE_EUR][0] == pytest.approx(1.50)

    promo_res = orchestrator.link_line("arroz basmati 1 kg", products, is_promo_member=True)
    assert promo_res[LineResultColumns.PRODUCT_ID][0] == "promo_cheaper"
    assert promo_res[LineResultColumns.EFFECTIVE_PRICE_EUR][0] == pytest.approx(1.20)
    assert promo_res[LineResultColumns.PRICE_PER_KG][0] == pytest.approx(1.20)
