import polars as pl

from supermarket_linkage.consts import JW_MAX_DISTANCE
from supermarket_linkage.pipeline.distance_stage import DistanceStage
from supermarket_linkage.schemas.candidate_table import CandidateColumns


def test_distance_stage_keeps_close_names() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1", "2"],
            CandidateColumns.NAME: ["Arroz basmati 1 kg", "Pan de molde"],
            CandidateColumns.NAME_NORM: ["arroz basmati 1 kg", "pan molde"],
            CandidateColumns.QUERY_NORM: ["arroz basmati", "arroz basmati"],
        }
    )
    out = DistanceStage().process(df)
    assert out.height == 1
    assert out[CandidateColumns.PRODUCT_ID][0] == "1"
    assert out[CandidateColumns.JW_DISTANCE][0] < JW_MAX_DISTANCE
    assert out[CandidateColumns.JW_SIMILARITY][0] == 1.0 - out[CandidateColumns.JW_DISTANCE][0]


def test_distance_stage_exact_zero_distance() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1"],
            CandidateColumns.NAME_NORM: ["leche entera"],
            CandidateColumns.QUERY_NORM: ["leche entera"],
        }
    )
    out = DistanceStage().process(df)
    assert out.height == 1
    assert out[CandidateColumns.JW_DISTANCE][0] == 0.0
    assert out[CandidateColumns.JW_SIMILARITY][0] == 1.0


def test_distance_stage_rejects_far() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1"],
            CandidateColumns.NAME_NORM: ["detergente liquido"],
            CandidateColumns.QUERY_NORM: ["arroz basmati"],
        }
    )
    out = DistanceStage().process(df)
    assert out.height == 0


def test_distance_stage_empty() -> None:
    assert DistanceStage().process(pl.DataFrame()).height == 0
