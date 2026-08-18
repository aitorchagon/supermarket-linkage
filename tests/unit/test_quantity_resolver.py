"""Unit tests for QuantityResolver."""

import polars as pl

from supermarket_linkage.preprocessors.quantity_resolver import (
    QuantityResolver,
    units_needed_for,
)
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable


def test_units_needed_1500g_vs_1kg() -> None:
    units, missing = units_needed_for(1.5, 1.0)
    assert units == 2
    assert missing is False


def test_units_needed_500g_vs_1kg() -> None:
    units, missing = units_needed_for(0.5, 1.0)
    assert units == 1
    assert missing is False


def test_units_needed_2_5l_vs_1l() -> None:
    units, missing = units_needed_for(2.5, 1.0)
    assert units == 3
    assert missing is False


def test_units_needed_missing_pack() -> None:
    units, missing = units_needed_for(1.5, None)
    assert units == 1
    assert missing is True


def test_process_1500g_vs_1kg_pack() -> None:
    df = pl.DataFrame(
        {
            LineResultColumns.LINE_INDEX: [0],
            LineResultColumns.QUERY: ["arroz basmati 1500 g"],
            LineResultColumns.NAME: ["Arroz basmati 1 kg"],
            LineResultColumns.REQUESTED_AMOUNT_KG: [1.5],
            LineResultColumns.EFFECTIVE_PRICE_EUR: [1.25],
        }
    )
    out = QuantityResolver().process(df)
    assert out[LineResultColumns.PACK_SIZE_KG][0] == 1.0
    assert out[LineResultColumns.UNITS_NEEDED][0] == 2
    assert out[LineResultColumns.PACK_SIZE_MISSING][0] is False
    assert out[LineResultColumns.LINE_TOTAL_PRICE_EUR][0] == 2.5


def test_process_uses_approx_weight_when_present() -> None:
    df = pl.DataFrame(
        {
            LineResultColumns.LINE_INDEX: [0],
            LineResultColumns.NAME: ["Something without size"],
            LineResultColumns.REQUESTED_AMOUNT_KG: [2.0],
            LineResultColumns.EFFECTIVE_PRICE_EUR: [3.0],
            "approx_weight_kg": [0.5],
        }
    )
    out = QuantityResolver().process(df)
    assert out[LineResultColumns.PACK_SIZE_KG][0] == 0.5
    assert out[LineResultColumns.UNITS_NEEDED][0] == 4
    assert out[LineResultColumns.LINE_TOTAL_PRICE_EUR][0] == 12.0


def test_process_missing_pack_flags_and_min_one() -> None:
    df = pl.DataFrame(
        {
            LineResultColumns.LINE_INDEX: [0],
            LineResultColumns.NAME: ["Estropajo"],
            LineResultColumns.REQUESTED_AMOUNT_KG: [1.5],
            LineResultColumns.EFFECTIVE_PRICE_EUR: [0.80],
        }
    )
    out = QuantityResolver().process(df)
    assert out[LineResultColumns.UNITS_NEEDED][0] == 1
    assert out[LineResultColumns.PACK_SIZE_MISSING][0] is True
    assert out[LineResultColumns.PACK_SIZE_KG][0] is None
    assert out[LineResultColumns.LINE_TOTAL_PRICE_EUR][0] == 0.80
    assert out.columns == LineResultTable.columns()


def test_process_zero_pack_falls_back_to_name() -> None:
    df = pl.DataFrame(
        {
            LineResultColumns.LINE_INDEX: [0],
            LineResultColumns.NAME: ["Arroz basmati 1 kg"],
            LineResultColumns.REQUESTED_AMOUNT_KG: [1.5],
            LineResultColumns.PACK_SIZE_KG: [0.0],
            LineResultColumns.EFFECTIVE_PRICE_EUR: [1.25],
        }
    )
    out = QuantityResolver().process(df)
    assert out[LineResultColumns.PACK_SIZE_KG][0] == 1.0
    assert out[LineResultColumns.UNITS_NEEDED][0] == 2
    assert out[LineResultColumns.PACK_SIZE_MISSING][0] is False


def test_process_zero_pack_unresolved_writes_null() -> None:
    df = pl.DataFrame(
        {
            LineResultColumns.LINE_INDEX: [0],
            LineResultColumns.NAME: ["Estropajo"],
            LineResultColumns.REQUESTED_AMOUNT_KG: [1.5],
            LineResultColumns.PACK_SIZE_KG: [0.0],
            LineResultColumns.EFFECTIVE_PRICE_EUR: [0.80],
        }
    )
    out = QuantityResolver().process(df)
    assert out[LineResultColumns.PACK_SIZE_KG][0] is None
    assert out[LineResultColumns.UNITS_NEEDED][0] == 1
    assert out[LineResultColumns.PACK_SIZE_MISSING][0] is True
