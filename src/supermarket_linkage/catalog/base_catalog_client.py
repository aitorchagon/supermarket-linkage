"""
Abstract catalog client: search terms → ProductTable rows.
"""

from __future__ import annotations

from typing import Optional
from abc import ABC, abstractmethod
from collections.abc import Sequence

import polars as pl


class BaseCatalogClient(ABC):
    """Fetch store catalog hits for one or many search queries."""

    @abstractmethod
    def search(self, query: str, *, postal_code: Optional[str] = None) -> pl.DataFrame:
        """
        Search one query.

        Pre: ``query`` is a non-empty search string (already extracted if needed).
        Post: ProductTable-shaped frame; empty if the store returned no hits.
        """

    @abstractmethod
    def search_batch(
        self,
        queries: Sequence[str],
        *,
        postal_code: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        Search many queries (chunked round-trips).

        Pre: ``queries`` may be empty or contain duplicates.
        Post: ProductTable rows with ``source_query`` set; empty frame if none.
        """
