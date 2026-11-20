from __future__ import annotations

from typing import Optional

import polars as pl

from supermarket_linkage.catalog.promo_policy import MercadonaPromoPolicy, PromoPolicy
from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.consts import (
    _MEASURE_ALIASES,
    MEASURE_KILO,
    MEASURE_LITRO,
    MEASURE_UNIDAD,
    _to_float,
    to_kg,
)
from supermarket_linkage.regex_consts import PACK_SIZE
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable


def canonicalize_unit_measure(raw: Optional[str]) -> Optional[str]:
    """
    This function maps catalog unit strings and reported aliases to either KILO, LITRO or UNIDAD."""
    if raw is None or raw == "":
        return None
    key = raw.strip().lower()
    if key in {MEASURE_KILO.lower(), MEASURE_LITRO.lower(), MEASURE_UNIDAD.lower()}:
        return key.upper()
    return _MEASURE_ALIASES.get(key)


def parse_weight_from_name(name: Optional[str]) -> Optional[float]:
    """
    We take the first pack_size match in product name and we return its kilogram equivalent
    """
    if not name:
        return None
    match = PACK_SIZE.search(name)
    if match is None:
        return None
    value = _to_float(match.group("value"))
    if value is None:
        return None
    return to_kg(value, match.group("unit"))


def _price_per_kg(
    measure: Optional[str],
    price_eur: Optional[float],
    unit_price_eur: Optional[float],
    weight_kg: Optional[float],
) -> Optional[float]:
    """
    This function allows to compute euros per kilo (or euros per liter, it is treated the same),
    it returns a null when it is unknown.
    """
    if measure in (MEASURE_KILO, MEASURE_LITRO):
        if unit_price_eur is not None:
            return float(unit_price_eur)
        if price_eur is not None and weight_kg is not None and weight_kg > 0:
            return float(price_eur) / float(weight_kg)
        return None

    if measure == MEASURE_UNIDAD:
        if price_eur is not None and weight_kg is not None and weight_kg > 0:
            return float(price_eur) / float(weight_kg)
        return None

    # If the measure is unknown (we do not have a price per kilogram measure), we only derive it if we have both price and weight.
    if price_eur is not None and weight_kg is not None and weight_kg > 0:
        return float(price_eur) / float(weight_kg)
    return None


class PriceNormalizer(BasePreprocessor):
    """
    This class allows to normalize ProductTable rows and create the following columns:
    unit_measure,
    approx_weight
    price per kilogram.
    """

    def __init__(
        self,
        *,
        promo_policy: Optional[PromoPolicy] = None,
        is_promo_member: bool = False,
    ) -> None:
        self.promo_policy = promo_policy or (MercadonaPromoPolicy() if is_promo_member else None)
        self.is_promo_member = is_promo_member

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function allows to fill unit_measure, approx_weight_kg and price_per_kg columns.
        """
        enforced = ProductTable.enforce_schema(df)

        measures: list[Optional[str]] = []
        weights: list[Optional[float]] = []
        prices_kg: list[Optional[float]] = []

        for row in enforced.iter_rows(named=True):
            measure = canonicalize_unit_measure(raw=row[ProductColumns.UNIT_MEASURE])
            existing_w = row[ProductColumns.APPROX_WEIGHT_KG]
            parsed_w = parse_weight_from_name(name=row[ProductColumns.NAME])
            weight = existing_w if existing_w is not None else parsed_w

            if weight is None and measure in (MEASURE_KILO, MEASURE_LITRO):
                weight = parsed_w

            if self.promo_policy is not None:
                effective_price = self.promo_policy.effective_price(row, self.is_promo_member)
                if row[ProductColumns.PROMO_PRICE_EUR] is not None:
                    if weight is not None and weight > 0 and effective_price is not None:
                        price_kg: Optional[float] = float(effective_price) / float(weight)
                    else:
                        price_kg = _price_per_kg(
                            measure,
                            effective_price,
                            row[ProductColumns.UNIT_PRICE_EUR],
                            weight,
                        )
                else:
                    price_kg = _price_per_kg(
                        measure,
                        effective_price,
                        row[ProductColumns.UNIT_PRICE_EUR],
                        weight,
                    )
            else:
                price_kg = _price_per_kg(
                    measure,
                    row[ProductColumns.PRICE_EUR],
                    row[ProductColumns.UNIT_PRICE_EUR],
                    weight,
                )

            if (
                price_kg is None
                and row[ProductColumns.PRICE_PER_KG] is not None
                and row[ProductColumns.PRICE_EUR] is None
                and row[ProductColumns.UNIT_PRICE_EUR] is None
            ):
                price_kg = row[ProductColumns.PRICE_PER_KG]

            measures.append(measure)
            weights.append(weight)
            prices_kg.append(price_kg)

        out = enforced.with_columns(
            [
                pl.Series(ProductColumns.UNIT_MEASURE, measures, dtype=pl.String),
                pl.Series(ProductColumns.APPROX_WEIGHT_KG, weights, dtype=pl.Float64),
                pl.Series(ProductColumns.PRICE_PER_KG, prices_kg, dtype=pl.Float64),
            ]
        )
        return ProductTable.enforce_schema(out)
