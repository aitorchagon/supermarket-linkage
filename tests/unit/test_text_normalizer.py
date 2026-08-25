import polars as pl

from supermarket_linkage.preprocessors.text_normalizer import (
    TextNormalizer,
    extract_search_alternatives,
    extract_search_query,
    normalize_text,
    parse_requested_amount_kg,
    rough_stem,
    strip_accents,
)


def test_strip_accents() -> None:
    assert strip_accents("Café Niño") == "Cafe Nino"


def test_normalize_text_lower_stopwords_punctuation() -> None:
    assert normalize_text("Leche de la Vaca!!!") == "leche vaca"


def test_normalize_text_drops_por_ciento_and_aliases_pasta() -> None:
    assert normalize_text("chocolate 80 por ciento") == "chocolate 80"
    assert normalize_text("Espaguetti Hacendado") == "spaghetti hacendado"


def test_normalize_text_aliases_boniato_and_nueces() -> None:
    assert normalize_text("Boniato") == "batata"
    assert normalize_text("Nueces peladas") == "nuez peladas"


def test_rough_stem_spanish_plurals() -> None:
    assert rough_stem("lentejas") == "lenteja"
    assert rough_stem("cocidas") == "cocida"
    assert rough_stem("filetes") == "filete"
    assert rough_stem("calabacines") == "calabacin"
    assert rough_stem("arroz") == "arroz"


def test_extract_search_query_drops_quantity() -> None:
    assert extract_search_query("Arroz Basmati 1500 g") == "arroz basmati"
    assert extract_search_query("leche entera 1,5l") == "leche entera"
    assert extract_search_query("huevos 24 unidades") == "huevos"
    assert extract_search_query("Repollo 1 unidad") == "repollo"
    assert extract_search_query("Nueces 1 paquete") == "nuez"
    assert extract_search_query("Queso fresco batido 2 paquetes") == "queso fresco batido"
    assert extract_search_query("yogur natural 24 unidades") == "yogur natural"
    assert extract_search_query("aceite 500 gramos") == "aceite"
    assert extract_search_query("agua 2 litros") == "agua"


def test_extract_search_alternatives_or_and_pasta() -> None:
    assert extract_search_alternatives("Leche o bebida vegetal 6l") == [
        "leche",
        "bebida vegetal",
    ]
    alts = extract_search_alternatives("Pasta integral 1kg")
    assert alts[0] == "pasta integral"
    assert "spaghetti integral" in alts
    assert "macarrones integral" in alts
    assert extract_search_alternatives("Boniato 3kg") == ["batata"]


def test_parse_requested_amount_kg() -> None:
    assert parse_requested_amount_kg("arroz basmati 1500 g") == 1.5
    assert parse_requested_amount_kg("leche 1.5 kg") == 1.5
    assert parse_requested_amount_kg("agua 2 l") == 2.0
    assert parse_requested_amount_kg("aceite 500ml") == 0.5
    assert parse_requested_amount_kg("aceite 500 gramos") == 0.5
    assert parse_requested_amount_kg("agua 2 litros") == 2.0
    assert parse_requested_amount_kg("sin cantidad") is None
    assert parse_requested_amount_kg("huevos 12 uds") is None
    assert parse_requested_amount_kg("huevos 24 unidades") is None
    assert parse_requested_amount_kg("repollo 1 unidad") is None
    assert parse_requested_amount_kg("nueces 1 paquete") is None


def test_process_adds_columns() -> None:
    df = pl.DataFrame(
        {
            "query": [
                "Arroz Basmati 1500 g",
                "Leche entera 1l",
                "pan",
                "yogur natural 24 unidades",
            ]
        }
    )
    out = TextNormalizer().process(df)
    assert out["search_query"].to_list() == [
        "arroz basmati",
        "leche entera",
        "pan",
        "yogur natural",
    ]
    assert out["query_norm"].to_list() == out["search_query"].to_list()
    assert out["requested_amount_kg"].to_list() == [1.5, 1.0, None, None]
    assert out["query"].to_list() == df["query"].to_list()
