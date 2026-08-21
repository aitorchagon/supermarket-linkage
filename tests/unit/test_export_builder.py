from supermarket_linkage.consts import MERCADONA_PRODUCT_URL_TEMPLATE
from supermarket_linkage.export.base_export_builder import CSV_COLUMNS
from supermarket_linkage.export.mercadona_export_builder import MercadonaExportBuilder
from supermarket_linkage.schemas.line_result_table import LineResultColumns

_BUILDER = MercadonaExportBuilder()

_MATCHED = {
    LineResultColumns.QUERY: "arroz basmati 1500 g",
    LineResultColumns.STATUS: "matched",
    LineResultColumns.PRODUCT_ID: "4245",
    LineResultColumns.NAME: "Arroz basmati 1 kg",
    LineResultColumns.BRAND: "Hacendado",
    LineResultColumns.UNITS_NEEDED: 2,
    LineResultColumns.PACK_SIZE_MISSING: False,
    LineResultColumns.EFFECTIVE_PRICE_EUR: 1.50,
    LineResultColumns.LINE_TOTAL_PRICE_EUR: 3.00,
    LineResultColumns.PRICE_PER_KG: 1.50,
    LineResultColumns.PRODUCT_URL: "https://tienda.mercadona.es/product/4245",
}

_NO_MATCH = {
    LineResultColumns.QUERY: "quinoa roja",
    LineResultColumns.STATUS: "no_match",
    LineResultColumns.PRODUCT_ID: None,
    LineResultColumns.NAME: None,
    LineResultColumns.UNITS_NEEDED: 1,
    LineResultColumns.PRODUCT_URL: None,
}


def test_product_url_from_id_when_url_missing() -> None:
    row = {LineResultColumns.PRODUCT_ID: "4245", LineResultColumns.PRODUCT_URL: None}
    assert _BUILDER.product_url(row) == MERCADONA_PRODUCT_URL_TEMPLATE.format(
        product_id="4245"
    )


def test_product_url_prefers_trusted_existing() -> None:
    row = {
        LineResultColumns.PRODUCT_ID: "1",
        LineResultColumns.PRODUCT_URL: "https://tienda.mercadona.es/product/4245",
    }
    assert _BUILDER.product_url(row) == "https://tienda.mercadona.es/product/4245"


def test_product_url_rejects_foreign_host() -> None:
    row = {
        LineResultColumns.PRODUCT_ID: "4245",
        LineResultColumns.PRODUCT_URL: "https://evil.example/product/4245",
    }
    assert _BUILDER.product_url(row) == MERCADONA_PRODUCT_URL_TEMPLATE.format(
        product_id="4245"
    )


def test_product_url_rejects_host_suffix_trick() -> None:
    row = {
        LineResultColumns.PRODUCT_ID: None,
        LineResultColumns.PRODUCT_URL: "https://tienda.mercadona.es.evil.example/x",
    }
    assert _BUILDER.product_url(row) is None


def test_product_url_rejects_non_digit_id() -> None:
    row = {
        LineResultColumns.PRODUCT_ID: "../etc/passwd",
        LineResultColumns.PRODUCT_URL: None,
    }
    assert _BUILDER.product_url(row) is None


def test_clipboard_includes_units_needed_and_url() -> None:
    text = _BUILDER.to_clipboard_text([_MATCHED])
    assert text.startswith("2 × Arroz basmati 1 kg")
    assert "https://tienda.mercadona.es/product/4245" in text


def test_clipboard_marks_no_match_without_url() -> None:
    text = _BUILDER.to_clipboard_text([_NO_MATCH])
    assert "Sin match: quinoa roja" in text
    assert "tienda.mercadona.es" not in text


def test_clipboard_joins_blocks() -> None:
    text = _BUILDER.to_clipboard_text([_MATCHED, _NO_MATCH])
    assert "2 × Arroz basmati 1 kg" in text
    assert "Sin match: quinoa roja" in text
    assert "\n\n" in text


def test_clipboard_empty() -> None:
    assert _BUILDER.to_clipboard_text([]) == ""


def test_csv_header_and_units_needed() -> None:
    csv_text = _BUILDER.to_csv([_MATCHED])
    header = csv_text.splitlines()[0]
    for col in CSV_COLUMNS:
        assert col in header
    assert "2" in csv_text
    assert "arroz basmati 1500 g" in csv_text
    assert "https://tienda.mercadona.es/product/4245" in csv_text


def test_csv_fills_url_from_product_id() -> None:
    row = dict(_MATCHED)
    row[LineResultColumns.PRODUCT_URL] = None
    csv_text = _BUILDER.to_csv([row])
    assert MERCADONA_PRODUCT_URL_TEMPLATE.format(product_id="4245") in csv_text


def test_csv_empty_still_has_header() -> None:
    csv_text = _BUILDER.to_csv([])
    assert csv_text.startswith("query,")
    assert LineResultColumns.UNITS_NEEDED in csv_text.splitlines()[0]
    assert len(csv_text.splitlines()) == 1


def test_product_links_skips_no_match_and_dedupes() -> None:
    duplicate = dict(_MATCHED)
    links = _BUILDER.product_links([_MATCHED, duplicate, _NO_MATCH])
    assert links == ["https://tienda.mercadona.es/product/4245"]
