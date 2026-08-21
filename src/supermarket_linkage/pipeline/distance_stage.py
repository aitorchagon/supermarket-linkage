from __future__ import annotations

import polars as pl
import polars_distance as pld

from supermarket_linkage.consts import JW_MAX_DISTANCE
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import normalize_text
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


class DistanceStage(BaseStage):
    """Keep candidates with Jaro-Winkler distance strictly below ``JW_MAX_DISTANCE``."""

    def __init__(self, max_distance: float = JW_MAX_DISTANCE) -> None:
        self.max_distance = max_distance

    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Compute JW distance/similarity and filter.

        Pre: ``query_norm`` and ``name`` / ``name_norm``.
        Post: CandidateTable with only rows under the distance cap.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        if CandidateColumns.NAME_NORM not in df.columns:
            df = df.with_columns(
                pl.col(CandidateColumns.NAME)
                .fill_null("")
                .map_elements(normalize_text, return_dtype=pl.String)
                .alias(CandidateColumns.NAME_NORM)
            )
        elif CandidateColumns.NAME in df.columns:
            df = df.with_columns(
                pl.when(
                    pl.col(CandidateColumns.NAME_NORM).is_null()
                    | (pl.col(CandidateColumns.NAME_NORM) == "")
                )
                .then(
                    pl.col(CandidateColumns.NAME)
                    .fill_null("")
                    .map_elements(normalize_text, return_dtype=pl.String)
                )
                .otherwise(pl.col(CandidateColumns.NAME_NORM))
                .alias(CandidateColumns.NAME_NORM)
            )

        candidates = df.with_columns(
            [
                pl.col(CandidateColumns.QUERY_NORM).fill_null("").alias("_query"),
                pl.col(CandidateColumns.NAME_NORM).fill_null("").alias("_name"),
            ]
        )
        distances = (
            candidates.with_columns(
                pld.col("_query")
                .dist_str.jaro_winkler(pl.col("_name"))
                .alias(CandidateColumns.JW_DISTANCE)
            )
            .with_columns(
                (1.0 - pl.col(CandidateColumns.JW_DISTANCE)).alias(
                    CandidateColumns.JW_SIMILARITY
                )
            )
            .drop(["_query", "_name"])
        )

        corrected = distances.filter(
            pl.col(CandidateColumns.JW_DISTANCE) < self.max_distance
        )
        return CandidateTable.enforce_schema(corrected)
