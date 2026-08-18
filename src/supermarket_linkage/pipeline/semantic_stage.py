"""Semantic stage: cosine similarity threshold with injectable embedder."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

import numpy as np
import polars as pl

from supermarket_linkage.consts import SEMANTIC_THRESHOLD
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


@runtime_checkable
class Embedder(Protocol):
    """Text → vectors. Inject a mock in tests; no model download required."""

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return shape ``(len(texts), dim)`` float array."""


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two 1-D vectors. Empty/zero → 0.0."""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class SemanticStage(BaseStage):
    """Keep candidates with cosine(query, name) ≥ ``SEMANTIC_THRESHOLD``."""

    def __init__(
        self,
        embedder: Embedder,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> None:
        self.embedder = embedder
        self.threshold = threshold

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Score and filter by cosine similarity.

        Pre: ``query_norm`` and ``name_norm`` (or ``name``); injectable ``embedder``.
        Post: Survivors with ``semantic_score`` set; score ≥ threshold.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        if CandidateColumns.QUERY_NORM not in df.columns:
            raise ValueError("SemanticStage requires 'query_norm'.")

        name_col = (
            CandidateColumns.NAME_NORM
            if CandidateColumns.NAME_NORM in df.columns
            else CandidateColumns.NAME
        )
        if name_col not in df.columns:
            raise ValueError("SemanticStage requires 'name_norm' or 'name'.")

        queries = [q or "" for q in df[CandidateColumns.QUERY_NORM].to_list()]
        names = [n or "" for n in df[name_col].to_list()]

        # Unique texts → one embed call for efficiency.
        unique: list[str] = list(dict.fromkeys([*queries, *names]))
        vectors = np.asarray(self.embedder.embed(unique), dtype=np.float64)
        if vectors.ndim != 2 or vectors.shape[0] != len(unique):
            raise ValueError(
                f"Embedder must return (n, dim); got shape {getattr(vectors, 'shape', None)}"
            )
        by_text = {t: vectors[i] for i, t in enumerate(unique)}

        scores = [
            cosine_similarity(by_text[q], by_text[n]) for q, n in zip(queries, names, strict=True)
        ]
        out = df.with_columns(
            pl.Series(CandidateColumns.SEMANTIC_SCORE, scores, dtype=pl.Float64)
        ).filter(pl.col(CandidateColumns.SEMANTIC_SCORE) >= self.threshold)
        return CandidateTable.enforce_schema(out)
