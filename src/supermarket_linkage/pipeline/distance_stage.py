from __future__ import annotations

import polars as pl
import polars_distance as pld

from supermarket_linkage.consts import JW_MAX_DISTANCE
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import normalize_text
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


class DistanceStage(BaseStage):
    """
    Score Jaro-Winkler and keep candidates that are close enough.

    Live Mercadona titles are long (brand + packaging). Full-string JW against a
    short query often exceeds ``JW_MAX_DISTANCE`` even when the heuristic already
    proved every query token is in the name. Those rows are kept: JW is still
    stored for ranking / tie-break. Semantic-only rows (no heuristic) still need
    JW strictly below the cap (false-friend referee).
    """

    def __init__(self, max_distance: float = JW_MAX_DISTANCE) -> None:
        self.max_distance = max_distance

    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Compute JW distance/similarity and filter.

        Pre: ``query_norm`` and ``name`` / ``name_norm``.
        Post: CandidateTable with JW fields; rows kept if JW < cap or heuristic_pass.
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

        close = pl.col(CandidateColumns.JW_DISTANCE) < self.max_distance
        if CandidateColumns.HEURISTIC_PASS in distances.columns:
            kept = distances.filter(
                close | (pl.col(CandidateColumns.HEURISTIC_PASS) == True)  # noqa: E712
            )
        else:
            kept = distances.filter(close)
        return CandidateTable.enforce_schema(kept)
