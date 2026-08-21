import polars as pl

from supermarket_linkage.preprocessors.text_normalizer import (
    TextNormalizer,
    extract_search_query,
    normalize_text,
    parse_requested_amount_kg,
    strip_accents,
)


def test_strip_accents() -> None:
    assert strip_accents("Café Niño") == "Cafe Nino"


def test_normalize_text_lower_stopwords_punctuation() -> None:
    assert normalize_text("Leche de la Vaca!!!") == "leche vaca"


def test_extract_search_query_drops_quantity() -> None:
    assert extract_search_query("Arroz Basmati 1500 g") == "arroz basmati"
    assert extract_search_query("leche entera 1,5l") == "leche entera"


def test_parse_requested_amount_kg() -> None:
    assert parse_requested_amount_kg("arroz basmati 1500 g") == 1.5
    assert parse_requested_amount_kg("leche 1.5 kg") == 1.5
    assert parse_requested_amount_kg("agua 2 l") == 2.0
    assert parse_requested_amount_kg("aceite 500ml") == 0.5
    assert parse_requested_amount_kg("sin cantidad") is None
    assert parse_requested_amount_kg("huevos 12 uds") is None


def test_process_adds_columns() -> None:
    df = pl.DataFrame(
        {
            "query": [
                "Arroz Basmati 1500 g",
                "Leche entera 1l",
                "pan",
            ]
        }
    )
    out = TextNormalizer().process(df)
    assert out["search_query"].to_list() == ["arroz basmati", "leche entera", "pan"]
    assert out["query_norm"].to_list() == out["search_query"].to_list()
    assert out["requested_amount_kg"].to_list() == [1.5, 1.0, None]
    assert out["query"].to_list() == df["query"].to_list()
