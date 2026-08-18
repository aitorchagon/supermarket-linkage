from __future__ import annotations
from typing import Optional
# The heuristic is that density is 1 for all the products, so one liter is one kg
# for ranking exclusively (we do not take into account physics, it is not necessary)
_TO_KG: dict[str, float] = {
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
