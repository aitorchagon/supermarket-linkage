"""Abstract preprocessor: DataFrame in, DataFrame out."""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class BasePreprocessor(ABC):
    """Transform a Polars DataFrame in place of a pipeline step."""

    @abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply this preprocessor.

        Pre: ``df`` has the columns this subclass expects.
        Post: New DataFrame with derived columns; row count unchanged.
        """
