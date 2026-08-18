from typing import (
    Any,
    Mapping,
)

from supermarket_linkage.schemas.line_result_table import LineResultColumns


def _units_needed(row: Mapping[str, Any]) -> int:
    """This is a sanitizer for units needed"""
    raw = row.get(LineResultColumns.UNITS_NEEDED)
    if raw is None or raw == "":
        return 1
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _csv_cell(value: Any) -> str:
    """This is a sanitizer for csv rows"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)