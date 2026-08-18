from __future__ import annotations

import polars as pl

from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import normalize_text
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


def _ensure_name_norm(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure ``name_norm`` is populated (from ``name`` when needed)."""
    if CandidateColumns.NAME in df.columns:
        existing = (
            df[CandidateColumns.NAME_NORM].to_list()
            if CandidateColumns.NAME_NORM in df.columns
            else [None] * df.height
        )
        names = df[CandidateColumns.NAME].to_list()
        norms = [
            (nn if nn else normalize_text(name or ""))
            for nn, name in zip(existing, names, strict=True)
        ]
        return df.with_columns(pl.Series(CandidateColumns.NAME_NORM, norms, dtype=pl.String))
    if CandidateColumns.NAME_NORM in df.columns:
        return df
    raise ValueError("HeuristicStage requires 'name' or 'name_norm'.")


def heuristic_pass(query_norm: str | None, name_norm: str | None) -> bool:
    """Exact match or every query token appears in the product name tokens."""
    q = (query_norm or "").strip()
    n = (name_norm or "").strip()
    if not q or not n:
        return False
    if q == n:
        return True
    name_tokens = set(n.split())
    q_tokens = q.split()
    return bool(q_tokens) and all(t in name_tokens for t in q_tokens)


class HeuristicStage(BaseStage):
    """Keep rows that pass exact-normalized or token-subset heuristic."""

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Set ``heuristic_pass`` and keep only True rows.

        Pre: ``query_norm`` plus ``name`` and/or ``name_norm``.
        Post: Candidate schema; only heuristic passers remain.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        if CandidateColumns.QUERY_NORM not in df.columns:
            raise ValueError("HeuristicStage requires 'query_norm'.")

        base = _ensure_name_norm(df)
        flags = [
            heuristic_pass(q, n)
            for q, n in zip(
                base[CandidateColumns.QUERY_NORM].to_list(),
                base[CandidateColumns.NAME_NORM].to_list(),
                strict=True,
            )
        ]
        out = base.with_columns(
            pl.Series(CandidateColumns.HEURISTIC_PASS, flags, dtype=pl.Boolean)
        ).filter(pl.col(CandidateColumns.HEURISTIC_PASS))
        return CandidateTable.enforce_schema(out)
