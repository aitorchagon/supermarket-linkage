from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class BaseStage(ABC):
    """
    This is a base class for a stage in a pipeline process, particularly associated
    to a rule-based record-linkage chain.
    """

    @abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function executes a stage. We should be having a polars DataFrame with the expected columns and
        return a polars DataFrame whose schema is compatible with CandidateTable.
        """
