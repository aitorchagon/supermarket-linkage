from __future__ import annotations

from typing import Sequence

import numpy as np
import polars as pl

from supermarket_linkage.consts import SEMANTIC_THRESHOLD
from supermarket_linkage.pipeline.semantic_stage import SemanticStage, cosine_similarity
from supermarket_linkage.schemas.candidate_table import CandidateColumns


class _DictEmbedder:
    """Fixed string → vector map for deterministic CI tests."""

    def __init__(self, mapping: dict[str, np.ndarray]) -> None:
        self.mapping = {k: np.asarray(v, dtype=np.float64) for k, v in mapping.items()}

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack([self.mapping[t] for t in texts], axis=0)


def test_cosine_similarity_identical() -> None:
    v = np.array([1.0, 0.0, 0.0])
    assert cosine_similarity(v, v) == 1.0


def test_cosine_similarity_orthogonal() -> None:
    assert cosine_similarity(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == 0.0


def test_semantic_stage_keeps_above_threshold() -> None:
    # query and good name share vector; bad name is orthogonal.
    embedder = _DictEmbedder(
        {
            "arroz basmati": np.array([1.0, 0.0, 0.0, 0.0]),
            "arroz basmati 1 kg": np.array([0.9, 0.1, 0.0, 0.0]),
            "leche entera 1 l": np.array([0.0, 0.0, 1.0, 0.0]),
        }
    )
    # Cosine(q, good) ≈ 0.994; cosine(q, bad) = 0.
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["good", "bad"],
            CandidateColumns.NAME_NORM: ["arroz basmati 1 kg", "leche entera 1 l"],
            CandidateColumns.QUERY_NORM: ["arroz basmati", "arroz basmati"],
        }
    )
    out = SemanticStage(embedder=embedder).process(df)
    assert out.height == 1
    assert out[CandidateColumns.PRODUCT_ID][0] == "good"
    assert out[CandidateColumns.SEMANTIC_SCORE][0] >= SEMANTIC_THRESHOLD


def test_semantic_stage_filters_below_threshold() -> None:
    embedder = _DictEmbedder(
        {
            "q": np.array([1.0, 0.0]),
            "n": np.array([0.5, 0.5]),  # cos ≈ 0.707 < 0.75
        }
    )
    df = pl.DataFrame(
        {
            CandidateColumns.PRODUCT_ID: ["1"],
            CandidateColumns.NAME_NORM: ["n"],
            CandidateColumns.QUERY_NORM: ["q"],
        }
    )
    out = SemanticStage(embedder=embedder).process(df)
    assert out.height == 0


def test_semantic_stage_empty() -> None:
    out = SemanticStage(embedder=_DictEmbedder({})).process(pl.DataFrame())
    assert out.height == 0
