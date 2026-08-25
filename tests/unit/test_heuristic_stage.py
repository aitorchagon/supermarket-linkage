import polars as pl

from supermarket_linkage.pipeline.heuristic_stage import HeuristicStage, heuristic_pass
from supermarket_linkage.schemas.candidate_table import CandidateColumns


def test_heuristic_exact_normalized() -> None:
    assert heuristic_pass("arroz basmati", "arroz basmati") is True


def test_heuristic_all_tokens_in_name() -> None:
    assert heuristic_pass("arroz basmati", "arroz basmati integral 1 kg") is True


def test_heuristic_rejects_partial_tokens() -> None:
    assert heuristic_pass("arroz basmati", "arroz redondo") is False


def test_heuristic_rejects_dish_that_merely_contains_product() -> None:
    assert (
        heuristic_pass(
            "arroz basmati",
            "pollo curry hacendado arroz basmati bandeja",
        )
        is False
    )


def test_heuristic_plural_matches_singular_catalog() -> None:
    assert heuristic_pass("lentejas cocidas", "lenteja cocida hacendado tarro") is True
    assert heuristic_pass("garbanzos cocidos", "garbanzo cocido hacendado tarro") is True
    assert heuristic_pass("platanos", "platano canarias igp pieza") is True
    assert heuristic_pass("calabacines", "calabacin") is True


def test_heuristic_format_prefix_allows_head_noun() -> None:
    assert heuristic_pass("avena", "copos avena sin gluten hacendado paquete") is True
    assert heuristic_pass("filete pollo", "filetes pechuga pollo") is True


def test_heuristic_batata_alias_and_nuez() -> None:
    assert heuristic_pass("batata", "batata bandeja") is True
    assert heuristic_pass("nuez", "nuez natural hacendado pelada") is True


def test_heuristic_rejects_empty() -> None:
    assert heuristic_pass("", "arroz") is False
    assert heuristic_pass("arroz", "") is False


def test_heuristic_stage_filters_and_flags() -> None:
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1", "2", "3"],
            CandidateColumns.NAME: [
                "Arroz basmati 1 kg",
                "Arroz redondo 1 kg",
                "Leche entera 1 l",
            ],
            CandidateColumns.QUERY_NORM: ["arroz basmati"] * 3,
            CandidateColumns.SOURCE_QUERY: ["arroz basmati"] * 3,
        }
    )
    out = HeuristicStage().process(df)
    assert out.height == 1
    assert out[CandidateColumns.PRODUCT_ID][0] == "1"
    assert out[CandidateColumns.HEURISTIC_PASS][0] is True
    assert out[CandidateColumns.NAME_NORM][0] == "arroz basmati 1 kg"


def test_heuristic_stage_empty() -> None:
    out = HeuristicStage().process(pl.DataFrame())
    assert out.height == 0
