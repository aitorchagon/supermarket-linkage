from __future__ import annotations

from typing import Dict, Optional

MEASURE_KILO = "KILO"
MEASURE_LITRO = "LITRO"
MEASURE_UNIDAD = "UNIDAD"

_MEASURE_ALIASES: Dict[str, str] = {
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

# Density ≈ 1 for ranking: 1 L treated as 1 kg (not physics, just price/kg).
_TO_KG: Dict[str, float] = {
    "kg": 1.0,
    "kilo": 1.0,
    "kilos": 1.0,
    "g": 0.001,
    "gr": 0.001,
    "gramo": 0.001,
    "gramos": 0.001,
    "l": 1.0,
    "litro": 1.0,
    "litros": 1.0,
    "ml": 0.001,
    "cl": 0.01,
}


def to_kg(value: float, unit: str) -> Optional[float]:
    """
    Convert mass or volume to a kilogram equivalent. None for unknown / count units.
    """
    factor = _TO_KG.get(unit.lower())
    if factor is None:
        return None
    return value * factor


def is_count_unit(unit: str) -> bool:
    """True for piece / pack count units (ud, unidad, …)."""
    u = unit.lower()
    return u in {"u", "ud", "uds", "unidad", "unidades"}


def _to_float(value: object = None, *, raw: object | None = None) -> Optional[float]:
    """
    Coerce catalog / paste values to float. None for empty, bool, or unparsable.

    Accepts positional ``value`` or keyword ``raw`` (call-site alias).
    """
    data = raw if raw is not None else value
    if data is None or data == "":
        return None
    if isinstance(data, bool):
        return None
    if isinstance(data, (int, float)):
        return float(data)
    try:
        return float(str(data).replace(",", "."))
    except (TypeError, ValueError):
        return None
