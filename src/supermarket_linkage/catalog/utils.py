from typing import Optional

from supermarket_linkage.preprocessors.consts import _to_float
from supermarket_linkage.regex_consts import WAREHOUSE

__all__ = ["_to_float", "sanitize_warehouse"]


def sanitize_warehouse(raw: Optional[str]) -> Optional[str]:
    """Accept only Mercadona-style warehouse codes (e.g. mad1)."""
    if raw is None:
        return None
    code = raw.strip().lower()
    if WAREHOUSE.fullmatch(code):
        return code
    return None
