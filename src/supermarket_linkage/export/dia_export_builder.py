"""Mercadona export: hardcoded product URL pattern only (no SSRF)."""

from __future__ import annotations

from typing import (
    Any, 
    Optional,
    Mapping,
)

from supermarket_linkage.export.base_export_builder import BaseExportBuilder


class DIAExportBuilder(BaseExportBuilder):
    """
    This is an ExportBuilder object that contains openable links with pack
    quantities from tienda.mercadona.es.
    """

    def product_url(self, row: Mapping[str, Any]) -> Optional[str]:
        raise NotImplementedError
