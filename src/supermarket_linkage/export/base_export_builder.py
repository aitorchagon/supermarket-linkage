from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import (
    Any, 
    Optional,
    Set,
    List,
)

from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.export.consts import (
    STATUS_NO_MATCH,
    CSV_COLUMNS,
)
from supermarket_linkage.export.utils import (
    _csv_cell,
    _units_needed
)

class BaseExportBuilder(ABC):
    """
    This is a base class for exporting public product URLS, CSVs or clipboard quantities.
    """

    @abstractmethod
    def product_url(self, row: Mapping[str, Any]) -> Optional[str]:
        """
        This function provides a public product URL for one result row, which is a LineResult dictionary
        (worker JSON). If there is no match or there is a missing id in the dictionary, we return None
        """

    def product_links(self, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        """
        This function provides unique product URLs in list order, skipping missing or no_match 
        products. 
        """
        seen: Set[str] = set()
        links: List[str] = []
        for row in rows:
            if str(row.get(LineResultColumns.STATUS) or "") == STATUS_NO_MATCH:
                continue
            url = self.product_url(row)
            if url and url not in seen:
                seen.add(url)
                links.append(url)
        return links

    def to_csv(self, rows: Sequence[Mapping[str, Any]]) -> str:
        """
        This function allows to create a CSV with pre-defined shopping columns out of LineResult dicts.
        """
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=list(CSV_COLUMNS),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            out = {col: _csv_cell(row.get(col)) for col in CSV_COLUMNS}
            out[LineResultColumns.PRODUCT_URL] = self.product_url(row) or ""
            out[LineResultColumns.UNITS_NEEDED] = _units_needed(row)
            writer.writerow(out)
        return buf.getvalue()

    def to_clipboard_text(self, rows: Sequence[Mapping[str, Any]]) -> str:
        """
        This function allows to create plain text with 
        ``units_needed × name`` and URL per matched line.
        """
        if not rows:
            return ""
        return "\n\n".join(self._clipboard_block(row) for row in rows)

    def _clipboard_block(self, row: Mapping[str, Any]) -> str:
        """
        This function allows to create plain text with a line that contains the unit needed
        per name and the URL.
        """
        status = str(row.get(LineResultColumns.STATUS) or "")
        query = str(row.get(LineResultColumns.QUERY) or "").strip()
        if status == STATUS_NO_MATCH:
            return f"— Sin match: {query or '(vacío)'}"
        name = str(row.get(LineResultColumns.NAME) or query or "producto").strip()
        lines = [f"{_units_needed(row)} × {name}"]
        url = self.product_url(row)
        if url:
            lines.append(url)
        return "\n".join(lines)

