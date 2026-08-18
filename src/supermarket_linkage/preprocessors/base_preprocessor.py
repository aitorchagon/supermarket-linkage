from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class BasePreprocessor(ABC):
    """
    This is a base preprocessor for polars DataFrames
    """

    @abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function applies the preprocessor. It expects a polars DataFrame 
        and it will transform it with derived columns, the row count should
        remain unchanged.
        """
