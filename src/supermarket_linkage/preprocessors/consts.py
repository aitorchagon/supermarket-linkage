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

# The heuristic is that density is 1 for all the products, so one liter is one kg
# for ranking exclusively (we do not take into account physics, it is not necessary)
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
    This function converts mass or volume to a kilogram equivalent, and returns None
    for unknown or unit counts.
    """
    factor = _TO_KG.get(unit.lower())
    if factor is None:
        return None
    return value * factor


def is_count_unit(unit: str) -> bool:
    """
    This function checks whether we have piece or pack count units.
    """
    u = unit.lower()
    return u in {"u", "ud", "uds", "unidad", "unidades"}