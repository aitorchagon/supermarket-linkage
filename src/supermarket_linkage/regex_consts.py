import re

POSTAL_CODE: re.Pattern[str] = re.compile(r"^\d{5}$")

WAREHOUSE: re.Pattern[str] = re.compile(r"^[a-z]{3}\d+$")

# Longest unit alternatives first + trailing \b so "24 unidades" does not
# match as "24 u", and "2 gramos" / "2 litros" are not truncated.
# Use ``unidades|unidad`` (not ``unidades?``): the latter is "unidade" + optional
# ``s`` and never matches Spanish singular ``unidad``.
_UNIT = (
    r"kg|kilos?|gramos?|gr|g|litros?|ml|cl|l|"
    r"unidades|unidad|paquetes|paquete|packs|pack|uds?|ud|u"
)

QUANTITY: re.Pattern[str] = re.compile(
    rf"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)

PACK_SIZE: re.Pattern[str] = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|kilos?|gramos?|gr|g|litros?|ml|cl|l)\b",
    re.IGNORECASE,
)

CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

NON_WORD: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)
