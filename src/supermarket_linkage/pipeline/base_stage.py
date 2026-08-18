from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl

from supermarket_linkage.schemas.candidate_table import CandidateColumns

class BaseStage(ABC):
    """
    This is a base class for a stage in a pipeline process, particularly associated
    to a rule-based record-linkage chain.
    """

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function executes a stage. We should be having a polars DataFrame with the expected columns and
        return a polars DataFrame whose schema is compatible with CandidateTable.
        """
        stage_name = self.__class__.__name__

        if CandidateColumns.QUERY_NORM not in df.columns:
            raise ValueError(f"{stage_name} requires 'query_norm'.")

        if CandidateColumns.NAME not in df.columns:
            raise ValueError(f"{stage_name} requires 'name'.")

        return self._process(df)
    
    @abstractmethod
    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        raise NotImplementedError