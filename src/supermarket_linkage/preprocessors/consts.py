from typing import Dict

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