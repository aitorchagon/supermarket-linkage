from __future__ import annotations

from typing import (
    Optional,
    Tuple,
    List,
)
import math

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.price_normalizer import parse_weight_from_name
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable


def units_for_total_weight(requested_kg: Optional[float], pack_kg: Optional[float]) -> Tuple[int, bool]:
    """
    This function allows to calculate how many units (packages) do we need to fulfill a requested total weight.
    We do not provide less than one unit. It returns a tuple that contains the units needed and whether
    we are missing a pack size.
    """
    pack_missing = pack_kg is None or pack_kg <= 0
    if pack_missing:
        return 1, True
    if requested_kg is None or requested_kg <= 0:
        return 1, False
    return max(1, math.ceil(requested_kg / pack_kg)), False


class QuantityResolver(BasePreprocessor):
    """
    This class allows to resolve a requested amount with a pack size
    after we have selected a final winner.
    """

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        It creates and fulfills the columns pack_size_kg, units_needed, totals and pack_size_missing,
        where totals refer to the total requested quantity. Originally, we have optional columns 
        requested_amount_kg, approx_weight_kg, pack_size_kg, name (name of product) and effective_price_eur.

        The minimum number of units provided is 1.
        """
        base = LineResultTable.enforce_schema(df)

        # Carry approx_weight_kg if present before enforce schema dropped it.
        approx_col = (
            df.get_column("approx_weight_kg")
            if "approx_weight_kg" in df.columns
            else pl.Series("approx_weight_kg", [None] * df.height)
        )

        units_list: List[int] = []
        pack_list: List[Optional[float]] = []
        missing_list: List[bool] = []
        total_list: List[Optional[float]] = []

        for i, row in enumerate(base.iter_rows(named=True)):
            requested = row[LineResultColumns.REQUESTED_AMOUNT_KG]
            pack = row[LineResultColumns.PACK_SIZE_KG]
            if pack is None or pack <= 0:
                approx = approx_col[i]
                if approx is not None and approx > 0:
                    pack = approx
                else:
                    pack = parse_weight_from_name(
                        name=row[LineResultColumns.NAME]
                    )

            units, pack_missing = units_for_total_weight(
                requested_kg=requested, 
                pack_kg=pack,
            )
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