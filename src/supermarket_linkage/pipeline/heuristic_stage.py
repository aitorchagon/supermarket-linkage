from __future__ import annotations

import polars as pl

from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import normalize_text
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


def heuristic_pass(query_norm: str | None, name_norm: str | None) -> bool:
    """
    Exact normalized match, or all query tokens ⊆ name tokens.
    """
    query_normalized = (query_norm or "").strip()
    name_normalized = (name_norm or "").strip()
    if not query_normalized or not name_normalized:
        return False
    if query_normalized == name_normalized:
        return True
    name_tokens = set(name_normalized.split())
    query_tokens = query_normalized.split()
    return bool(query_tokens) and all(token in name_tokens for token in query_tokens)


class HeuristicStage(BaseStage):
    """Keep rows that pass exact-normalized or token-subset heuristic."""

    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Set ``heuristic_pass`` and keep only True rows.

        Pre: ``query_norm`` plus ``name`` and/or ``name_norm``.
        Post: Candidate schema; only heuristic passers remain.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        if CandidateColumns.NAME in df.columns:
            if CandidateColumns.NAME_NORM in df.columns:
                norms = [
                    (nn if nn else normalize_text(name or ""))
                    for nn, name in zip(
                        df[CandidateColumns.NAME_NORM].to_list(),
                        df[CandidateColumns.NAME].to_list(),
                        strict=True,
                    )
                ]
            else:
                norms = [
                    normalize_text(name or "")
                    for name in df[CandidateColumns.NAME].to_list()
                ]
            df = df.with_columns(
                pl.Series(CandidateColumns.NAME_NORM, norms, dtype=pl.String)
            )
        elif CandidateColumns.NAME_NORM not in df.columns:
            raise ValueError("HeuristicStage requires 'name' or 'name_norm'.")

        flags = [
            heuristic_pass(query_norm=query_normalized, name_norm=name_normalized)
            for query_normalized, name_normalized in zip(
                df[CandidateColumns.QUERY_NORM].to_list(),
                df[CandidateColumns.NAME_NORM].to_list(),
                strict=True,
            )
        ]
        final = df.with_columns(
            pl.Series(CandidateColumns.HEURISTIC_PASS, flags, dtype=pl.Boolean)
        ).filter(pl.col(CandidateColumns.HEURISTIC_PASS))
        return CandidateTable.enforce_schema(final)
