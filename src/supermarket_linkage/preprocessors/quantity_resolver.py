"""Compute units_needed and line totals after a product winner is chosen."""

from __future__ import annotations

import math

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.price_normalizer import parse_weight_from_name
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable


def units_needed_for(requested_kg: float | None, pack_kg: float | None) -> tuple[int, bool]:
    """Ceil(requested / pack), minimum 1.

    Returns ``(units_needed, pack_size_missing)``.
    Missing pack → (1, True). Missing/zero requested → (1, pack_missing).
    """
    pack_missing = pack_kg is None or pack_kg <= 0
    if pack_missing:
        return 1, True
    if requested_kg is None or requested_kg <= 0:
        return 1, False
    return max(1, math.ceil(requested_kg / pack_kg)), False


class QuantityResolver(BasePreprocessor):
    """Fulfill requested amount with pack size after winner selection."""

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Set ``pack_size_kg``, ``units_needed``, totals, ``pack_size_missing``.

        Pre: Rows with optional ``requested_amount_kg``, ``approx_weight_kg`` /
        ``pack_size_kg``, ``name``, ``effective_price_eur``.
        Post: ``LineResultTable.enforce_schema``; min units is 1.
        """
        base = LineResultTable.enforce_schema(df)

        # Carry approx_weight_kg if present before enforce dropped it.
        approx_col = (
            df.get_column("approx_weight_kg")
            if "approx_weight_kg" in df.columns
            else pl.Series("approx_weight_kg", [None] * df.height)
        )

        units_list: list[int] = []
        pack_list: list[float | None] = []
        missing_list: list[bool] = []
        total_list: list[float | None] = []

        for i, row in enumerate(base.iter_rows(named=True)):
            requested = row[LineResultColumns.REQUESTED_AMOUNT_KG]
            pack = row[LineResultColumns.PACK_SIZE_KG]
            if pack is None or pack <= 0:
                approx = approx_col[i]
                if approx is not None and approx > 0:
                    pack = approx
                else:
                    pack = parse_weight_from_name(row[LineResultColumns.NAME])

            units, pack_missing = units_needed_for(requested, pack)
            if pack_missing:
                pack = None
            price = row[LineResultColumns.EFFECTIVE_PRICE_EUR]
            total = (units * price) if price is not None else None

            units_list.append(units)
            pack_list.append(pack)
            missing_list.append(pack_missing)
            total_list.append(total)

        out = base.with_columns(
            [
                pl.Series(LineResultColumns.PACK_SIZE_KG, pack_list, dtype=pl.Float64),
                pl.Series(LineResultColumns.UNITS_NEEDED, units_list, dtype=pl.Int64),
                pl.Series(LineResultColumns.PACK_SIZE_MISSING, missing_list, dtype=pl.Boolean),
                pl.Series(
                    LineResultColumns.LINE_TOTAL_PRICE_EUR, total_list, dtype=pl.Float64
                ),
            ]
        )
        return LineResultTable.enforce_schema(out)
