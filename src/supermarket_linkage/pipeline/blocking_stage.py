"""Blocking stage: keep candidates from the same source_query block."""

from __future__ import annotations

import polars as pl

from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


class BlockingStage(BaseStage):
    """
    This stage allows to keep candidates from the same source_query block, that is, keep the rows
    whose source query matches the line query_norm.
    """

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function allows to filter to a current query's search block. We have
        source_query and query_norm columns and, as a result, we only have the rows that correspond to the same 
        block.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        for col in (CandidateColumns.SOURCE_QUERY, CandidateColumns.QUERY_NORM):
            if col not in df.columns:
                raise ValueError(f"BlockingStage requires '{col}'.")

        out = df.filter(
            pl.col(CandidateColumns.SOURCE_QUERY) == pl.col(CandidateColumns.QUERY_NORM)
        )
        return CandidateTable.enforce_schema(out)
