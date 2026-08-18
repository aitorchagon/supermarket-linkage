"""Simple regex patterns. Cap input length (MAX_LINE_LENGTH) to limit ReDoS risk."""

import re

# Spanish 5-digit postal code
POSTAL_CODE: re.Pattern[str] = re.compile(r"^\d{5}$")

# Mercadona warehouse codes (mad1, vlc1, bcn1, …) — reject anything else
WAREHOUSE: re.Pattern[str] = re.compile(r"^[a-z]{3}\d+$")

# Quantity in list lines, e.g. "1500 g", "1.5 kg", "2 l"
QUANTITY: re.Pattern[str] = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|kilos?|g|gr|gramos?|l|litros?|ml|cl|ud?s?|unidades?)",
    re.IGNORECASE,
)

# Pack size in product names, e.g. "1 Kg aprox.", "500 g"
PACK_SIZE: re.Pattern[str] = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|kilos?|g|gr|gramos?|l|litros?|ml|cl)\b",
    re.IGNORECASE,
)

# Control characters except newline, carriage return, tab
CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Non-word noise (accents handled separately via NFKD in the normalizer)
NON_WORD: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)
