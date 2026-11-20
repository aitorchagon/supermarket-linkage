"""Mercadona export: hardcoded product URL pattern only (no SSRF)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
)

from supermarket_linkage.export.base_export_builder import BaseExportBuilder


class CarrefourExportBuilder(BaseExportBuilder):
    """
    This is an ExportBuilder object that contains openable links with pack
    quantities from tienda.mercadona.es.
    """

    def product_url(self, row: Mapping[str, Any]) -> str | None:
        raise NotImplementedError
