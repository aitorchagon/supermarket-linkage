from __future__ import annotations

import polars as pl
import polars_distance as pld

from supermarket_linkage.consts import JW_MAX_DISTANCE
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import normalize_text
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


class DistanceStage(BaseStage):
    """
    This stage is in charge of keeping the candidates that have a Jaro-Winkler distance
    lower than JW_MAX_DISTANCE.
    """

    def __init__(self, max_distance: float = JW_MAX_DISTANCE) -> None:
        self.max_distance = max_distance

    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Here, we compute the Jaro-Winkler similarity and perform a filter.
        
        Arguments
        ---------
        df: This is a polars DataFrame that should contain the columns query_norm and name_norm/name.
        
        Returns
        ---------
        It returns a CandidateTable object that contains the chosen candidates according to the heuristic
        we have defined.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        if CandidateColumns.NAME_NORM not in df.columns:
            normalized = [normalize_text(n or "") for n in df[CandidateColumns.NAME].to_list()]
            df = df.with_columns(
                pl.Series(CandidateColumns.NAME_NORM, normalized, dtype=pl.String)
            )
        else:
            # Fill null normalized from name when available.
            if CandidateColumns.NAME in df.columns:
                filled = [
                    (null_normalized if null_normalized else normalize_text(name or ""))
                    for null_normalized, name in zip(
                        df[CandidateColumns.NAME_NORM].to_list(),
                        df[CandidateColumns.NAME].to_list(),
                        strict=True,
                    )
                ]
                df = df.with_columns(
                    pl.Series(CandidateColumns.NAME_NORM, filled, dtype=pl.String)
                )

        # Null-safe strings for the plugin.
        candidates = df.with_columns(
            [
                pl.col(CandidateColumns.QUERY_NORM).fill_null("").alias("_query"),
                pl.col(CandidateColumns.NAME_NORM).fill_null("").alias("_name"),
            ]
        )
        distances = candidates.with_columns(
            pld.col("_query")
            .dist_str.jaro_winkler(pl.col("_name"))
            .alias(CandidateColumns.JW_DISTANCE)
        ).with_columns(
            (1.0 - pl.col(CandidateColumns.JW_DISTANCE)).alias(CandidateColumns.JW_SIMILARITY)
        ).drop(["_query", "_name"])

        corrected = distances.filter(pl.col(CandidateColumns.JW_DISTANCE) < self.max_distance)
        return CandidateTable.enforce_schema(corrected)
