"""Unit tests for PriceNormalizer."""

import polars as pl

from supermarket_linkage.preprocessors.price_normalizer import (
    PriceNormalizer,
    canonicalize_unit_measure,
    parse_weight_from_name,
)
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable


def test_canonicalize_unit_measure() -> None:
    assert canonicalize_unit_measure("kilo") == "KILO"
    assert canonicalize_unit_measure("KG") == "KILO"
    assert canonicalize_unit_measure("litro") == "LITRO"
    assert canonicalize_unit_measure("ud") == "UNIDAD"
    assert canonicalize_unit_measure(None) is None


def test_parse_weight_from_name() -> None:
    assert parse_weight_from_name("Arroz basmati 1 Kg") == 1.0
    assert parse_weight_from_name("Plátano 1 Kg aprox.") == 1.0
    assert parse_weight_from_name("Aceite 500 ml") == 0.5
    assert parse_weight_from_name("Sin peso") is None


def test_kilo_uses_unit_price() -> None:
    df = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["1"],
            ProductColumns.NAME: ["Plátano"],
            ProductColumns.PRICE_EUR: [1.20],
            ProductColumns.UNIT_PRICE_EUR: [1.99],
            ProductColumns.UNIT_MEASURE: ["KILO"],
        }
    )
    out = PriceNormalizer().process(df)
    assert out[ProductColumns.UNIT_MEASURE][0] == "KILO"
    assert out[ProductColumns.PRICE_PER_KG][0] == 1.99


def test_litro_treated_as_price_per_kg() -> None:
    df = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["2"],
            ProductColumns.NAME: ["Leche entera 1 L"],
            ProductColumns.PRICE_EUR: [0.90],
            ProductColumns.UNIT_PRICE_EUR: [0.90],
            ProductColumns.UNIT_MEASURE: ["litro"],
        }
    )
    out = PriceNormalizer().process(df)
    assert out[ProductColumns.UNIT_MEASURE][0] == "LITRO"
    assert out[ProductColumns.PRICE_PER_KG][0] == 0.90
    assert out[ProductColumns.APPROX_WEIGHT_KG][0] == 1.0


def test_unidad_derives_from_name_weight() -> None:
    df = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["3"],
            ProductColumns.NAME: ["Arroz basmati 1 kg"],
            ProductColumns.PRICE_EUR: [1.50],
            ProductColumns.UNIT_MEASURE: ["UNIDAD"],
        }
    )
    out = PriceNormalizer().process(df)
    assert out[ProductColumns.APPROX_WEIGHT_KG][0] == 1.0
    assert out[ProductColumns.PRICE_PER_KG][0] == 1.50


def test_unidad_without_weight_is_null_price_per_kg() -> None:
    df = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["4"],
            ProductColumns.NAME: ["Estropajo"],
            ProductColumns.PRICE_EUR: [0.80],
            ProductColumns.UNIT_MEASURE: ["UNIDAD"],
        }
    )
    out = PriceNormalizer().process(df)
    assert out[ProductColumns.APPROX_WEIGHT_KG][0] is None
    assert out[ProductColumns.PRICE_PER_KG][0] is None


def test_enforce_product_schema() -> None:
    df = pl.DataFrame(
        {
            ProductColumns.PRODUCT_ID: ["5"],
            ProductColumns.NAME: ["Harina 500 g"],
            ProductColumns.PRICE_EUR: [0.70],
            ProductColumns.UNIT_MEASURE: ["unidad"],
        }
    )
    out = PriceNormalizer().process(df)
    assert out.columns == ProductTable.columns()
    assert out[ProductColumns.PRICE_PER_KG][0] == 1.4  # 0.70 / 0.5
