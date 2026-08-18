"""Mercadona export: hardcoded product URL pattern only (no SSRF)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from supermarket_linkage.consts import (
    MERCADONA_PRODUCT_URL_PREFIX,
    MERCADONA_PRODUCT_URL_TEMPLATE,
)
from supermarket_linkage.export.base_export_builder import BaseExportBuilder
from supermarket_linkage.schemas.line_result_table import LineResultColumns


class MercadonaExportBuilder(BaseExportBuilder):
    """
    This is an ExportBuilder object that contains openable links with pack
    quantities from tienda.mercadona.es.
    """

    def product_url(self, row: Mapping[str, Any]) -> Optional[str]:
        """
        This is a function that uses a trusted existing URL; if we do not have it,
        we use ``/product/{id}`` for digit ids.

        It returns a URL on the mercadona host if it exists, if not we return None. User hosts are ignored.
        """
        existing = row.get(LineResultColumns.PRODUCT_URL)
        if isinstance(existing, str):
            url = existing.strip()
            if url.startswith(MERCADONA_PRODUCT_URL_PREFIX):
                return url
        raw_id = row.get(LineResultColumns.PRODUCT_ID)
        if raw_id is None:
            return None
        product_id = str(raw_id).strip()
        if not product_id.isdigit():
            return None
        return MERCADONA_PRODUCT_URL_TEMPLATE.format(product_id=product_id)
