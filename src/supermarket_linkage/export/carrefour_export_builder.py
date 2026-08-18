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


class CarrefourExportBuilder(BaseExportBuilder):
    """
    This is an ExportBuilder object that contains openable links with pack
    quantities from tienda.mercadona.es.
    """

    def product_url(self, row: Mapping[str, Any]) -> Optional[str]:
        raise NotImplementedError
