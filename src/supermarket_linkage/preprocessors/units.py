"""Shared mass/volume conversion to a kg-equivalent base."""

from __future__ import annotations

# Density 1.0: 1 L ↔ 1 kg for ranking / quantity math.
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


def parse_numeric(raw: str) -> float | None:
    """Parse a decimal string that may use comma as separator."""
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_kg(value: float, unit: str) -> float | None:
    """Convert mass/volume to kg-equivalent. None for unknown / unit counts."""
    factor = _TO_KG.get(unit.lower())
    if factor is None:
        return None
    return value * factor


def is_count_unit(unit: str) -> bool:
    """True for piece/pack count units (ud, unidad, …)."""
    u = unit.lower()
    return u in {"u", "ud", "uds", "unidad", "unidades"}
