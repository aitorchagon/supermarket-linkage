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
        Run the stage. Empty frames skip column checks and go to ``_process``.
        Non-empty frames need ``query_norm`` and ``name`` or ``name_norm``.
        """
        stage_name = self.__class__.__name__

        if df.height == 0:
            return self._process(df)

        if CandidateColumns.QUERY_NORM not in df.columns:
            raise ValueError(f"{stage_name} requires 'query_norm'.")

        has_name = CandidateColumns.NAME in df.columns
        has_name_norm = CandidateColumns.NAME_NORM in df.columns
        if not has_name and not has_name_norm:
            raise ValueError(f"{stage_name} requires 'name' or 'name_norm'.")

        return self._process(df)
    
    @abstractmethod
    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        raise NotImplementedError