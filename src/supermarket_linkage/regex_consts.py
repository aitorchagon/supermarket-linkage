import re

POSTAL_CODE: re.Pattern[str] = re.compile(r"^\d{5}$")

WAREHOUSE: re.Pattern[str] = re.compile(r"^[a-z]{3}\d+$")

QUANTITY: re.Pattern[str] = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|kilos?|g|gr|gramos?|l|litros?|ml|cl|ud?s?|unidades?)",
    re.IGNORECASE,
)

PACK_SIZE: re.Pattern[str] = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|kilos?|g|gr|gramos?|l|litros?|ml|cl)\b",
    re.IGNORECASE,
)

CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

NON_WORD: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)
