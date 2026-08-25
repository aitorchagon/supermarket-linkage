from __future__ import annotations

from typing import (
    List,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np
import polars as pl
from numpy.typing import NDArray

from supermarket_linkage.consts import SEMANTIC_THRESHOLD
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.preprocessors.text_normalizer import strip_accents
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


@runtime_checkable
class Embedder(Protocol):
    """
    Convert texts to embedding vectors. Inject a mock in tests to avoid model download.
    """

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Return shape ``(len(texts), dim)`` float array."""


def cosine_similarity(a: NDArray[np.floating], b: NDArray[np.floating]) -> float:
    """
    Cosine similarity of two 1-d vectors. Empty or zero vectors → 0.0.
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _name_embed_variants(name: str | None, name_norm: str | None) -> List[str]:
    """
    MiniLM is sensitive to casing/accents on some Spanish titles. Score the best
    of display name, accent-stripped lowercase, and token name_norm.
    """
    variants: List[str] = []
    if name:
        variants.append(name)
        variants.append(strip_accents(name).lower())
    if name_norm:
        variants.append(name_norm)
    return list(dict.fromkeys(v for v in variants if v))


class SemanticStage(BaseStage):
    """
    Score cosine similarity; keep rows at/above threshold **or** heuristic pass.

    Heuristic survivors often have short queries vs long Mercadona titles, so
    cosine alone can drop true SKUs. Those rows stay; score is still stored.
    """

    def __init__(
        self,
        embedder: Embedder,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> None:
        self.embedder = embedder
        self.threshold = threshold

    def _process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Score cosine similarity and keep rows at or above the threshold,
        or rows that already passed the token heuristic.

        Pre: ``query_norm`` and ``name`` and/or ``name_norm``; injectable embedder.
        Post: CandidateTable with ``semantic_score``; filtered as above.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)

        queries = [q or "" for q in df[CandidateColumns.QUERY_NORM].to_list()]
        raw_names = (
            df[CandidateColumns.NAME].to_list()
            if CandidateColumns.NAME in df.columns
            else [None] * df.height
        )
        norm_names = (
            df[CandidateColumns.NAME_NORM].to_list()
            if CandidateColumns.NAME_NORM in df.columns
            else [None] * df.height
        )
        per_row_variants = [
            _name_embed_variants(
                name if isinstance(name, str) else None,
                norm if isinstance(norm, str) else None,
            )
            for name, norm in zip(raw_names, norm_names, strict=True)
        ]

        unique: List[str] = list(
            dict.fromkeys(
                [q for q in queries if q]
                + [v for variants in per_row_variants for v in variants]
            )
        )
        if not unique:
            return CandidateTable.as_empty_dataframe()

        embeddings = np.asarray(self.embedder.embed(unique), dtype=np.float64)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(unique):
            raise ValueError(
                f"Embedder must return (n, dim); got shape {getattr(embeddings, 'shape', None)}"
            )
        by_text = {t: embeddings[i] for i, t in enumerate(unique)}

        scores: List[float] = []
        for query, variants in zip(queries, per_row_variants, strict=True):
            if not query or query not in by_text or not variants:
                scores.append(0.0)
                continue
            q_vec = by_text[query]
            scores.append(
                max(cosine_similarity(q_vec, by_text[v]) for v in variants if v in by_text)
            )

        scored = df.with_columns(
            pl.Series(CandidateColumns.SEMANTIC_SCORE, scores, dtype=pl.Float64)
        )
        above = pl.col(CandidateColumns.SEMANTIC_SCORE) >= self.threshold
        if CandidateColumns.HEURISTIC_PASS in scored.columns:
            kept = scored.filter(
                above | (pl.col(CandidateColumns.HEURISTIC_PASS) == True)  # noqa: E712
            )
        else:
            kept = scored.filter(above)
        return CandidateTable.enforce_schema(kept)
