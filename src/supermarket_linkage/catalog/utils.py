from typing import (
    Any,
    Optional,
)

from supermarket_linkage.regex_consts import WAREHOUSE

def _to_float(value: Any) -> Optional[float]:
    """
    This function is created becaused the instructions can come in different sizes and ways,
    because it can be None, empty, a boolean, a number,...
    As a result, we deal with all the problematics so we can return a float only if necessary and
    deal with possible errors or return a None if anything can be inferred.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def sanitize_warehouse(raw: Optional[str]) -> Optional[str]:
    """
    This function allows to accept only Mercadona-style warehouse codes (e.g. mad1).
    """
    if raw is None:
        return None
    code = raw.strip().lower()
    if WAREHOUSE.fullmatch(code):
        return code
    return None