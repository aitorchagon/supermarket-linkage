"""Fill approx_weight_kg and price_per_kg from unit measure + product name."""

from __future__ import annotations

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.units import parse_numeric, to_kg
from supermarket_linkage.regex_consts import PACK_SIZE
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable

MEASURE_KILO = "KILO"
MEASURE_LITRO = "LITRO"
MEASURE_UNIDAD = "UNIDAD"

_MEASURE_ALIASES: dict[str, str] = {
    "kilo": MEASURE_KILO,
    "kilos": MEASURE_KILO,
    "kg": MEASURE_KILO,
    "litro": MEASURE_LITRO,
    "litros": MEASURE_LITRO,
    "l": MEASURE_LITRO,
    "liter": MEASURE_LITRO,
    "litre": MEASURE_LITRO,
    "unidad": MEASURE_UNIDAD,
    "unidades": MEASURE_UNIDAD,
    "ud": MEASURE_UNIDAD,
    "uds": MEASURE_UNIDAD,
    "u": MEASURE_UNIDAD,
}


def canonicalize_unit_measure(raw: str | None) -> str | None:
    """Map catalog unit strings to KILO / LITRO / UNIDAD."""
    if raw is None or raw == "":
        return None
    key = raw.strip().lower()
    if key in {MEASURE_KILO.lower(), MEASURE_LITRO.lower(), MEASURE_UNIDAD.lower()}:
        return key.upper()
    return _MEASURE_ALIASES.get(key)


def parse_weight_from_name(name: str | None) -> float | None:
    """First PACK_SIZE match in product name → kg-equivalent."""
    if not name:
        return None
    match = PACK_SIZE.search(name)
    if match is None:
        return None
    value = parse_numeric(match.group("value"))
    if value is None:
        return None
    return to_kg(value, match.group("unit"))


def _price_per_kg(
    measure: str | None,
    price_eur: float | None,
    unit_price_eur: float | None,
    weight_kg: float | None,
) -> float | None:
    """Compute €/kg (L treated as kg). Null when unknown."""
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

    # Unknown measure: only derive if we have both price and weight.
    if price_eur is not None and weight_kg is not None and weight_kg > 0:
        return float(price_eur) / float(weight_kg)
    return None


class PriceNormalizer(BasePreprocessor):
    """Normalize ProductTable rows: unit measure, approx weight, price/kg."""

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Fill ``unit_measure``, ``approx_weight_kg``, ``price_per_kg``.

        Pre: Product-like columns (at least ``name`` / prices useful when present).
        Post: ``ProductTable.enforce_schema`` applied; unknown price/kg → null.
        """
        enforced = ProductTable.enforce_schema(df)

        measures: list[str | None] = []
        weights: list[float | None] = []
        prices_kg: list[float | None] = []

        for row in enforced.iter_rows(named=True):
            measure = canonicalize_unit_measure(row[ProductColumns.UNIT_MEASURE])
            existing_w = row[ProductColumns.APPROX_WEIGHT_KG]
            parsed_w = parse_weight_from_name(row[ProductColumns.NAME])
            weight = existing_w if existing_w is not None else parsed_w

            # KILO/LITRO sold "aprox." still benefit from name weight when missing.
            if weight is None and measure in (MEASURE_KILO, MEASURE_LITRO):
                weight = parsed_w

            price_kg = _price_per_kg(
                measure,
                row[ProductColumns.PRICE_EUR],
                row[ProductColumns.UNIT_PRICE_EUR],
                weight,
            )

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
