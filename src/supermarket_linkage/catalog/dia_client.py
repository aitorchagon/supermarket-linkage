"""DIA catalog stub (v1). Still not implemented, to be made in the future"""

from __future__ import annotations

from typing import Optional
from collections.abc import Sequence

import polars as pl

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.catalog.consts import (DIA_NOT_IMPLEMENTED_MESSAGE)


class DiaCatalogClient(BaseCatalogClient):
    """Placeholder until a DIA client exists (Playwright)."""

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def search(self, query: str, *, postal_code: Optional[str] = None) -> pl.DataFrame:
        raise NotImplementedError(DIA_NOT_IMPLEMENTED_MESSAGE)

    def search_batch(
        self,
        queries: Sequence[str],
        *,
        postal_code: Optional[str] = None,
    ) -> pl.DataFrame:
        raise NotImplementedError(DIA_NOT_IMPLEMENTED_MESSAGE)
