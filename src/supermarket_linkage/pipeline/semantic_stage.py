from __future__ import annotations

from typing import (
    Protocol, 
    Sequence, 
    runtime_checkable,
    List,
)

import numpy as np
from numpy.typing import NumpyArray
import polars as pl

from supermarket_linkage.consts import SEMANTIC_THRESHOLD
from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable


@runtime_checkable # to be able to apply isinstance, to check existence
# we use protocol to check whether any of the embedder we are adding has the function embed,
# because embedder is not a parent of any of them
class Embedder(Protocol):
    """
    This class allows to convert a text to tokens. It injects a mock in tests so we do not
    require to download a model for that.
    """
    
    def embed(self, texts: Sequence[str]) -> NumpyArray[np.float32]:
        """Return shape ``(len(texts), dim)`` float array."""


def cosine_similarity(a: NumpyArray[np.float32], b: NumpyArray[np.float32]) -> float:
    """
    This function calculates the cosine similarity of two 1 dimensional vectors. 
    Empty or zero vectors provide a similarity of zero for numerical stability.
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class SemanticStage(BaseStage):
    """
    This stage executes the semantic step, and allows to keep candidates whose cosine similarity
    is higher or equal than SEMANTIC_THRESHOLD.
    """

    def __init__(
        self,
        embedder: Embedder,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> None:
        self.embedder = embedder
        self.threshold = threshold

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        This function calculates the cosine similarity score and filter the candidates. 
        At the beginning, we have the columns query_norm and name_norm or name in the polars DataFrame (df), as
        well as an injectable embedder; at the end, we keep the winners whose semantic_score, set throughout the process
        is higher or equal than the threshold.
        """
        if df.height == 0:
            return CandidateTable.enforce_schema(df)
        
        name_col = (
            CandidateColumns.NAME_NORM
            if CandidateColumns.NAME_NORM in df.columns
            else CandidateColumns.NAME
        )

        queries = [q or "" for q in df[CandidateColumns.QUERY_NORM].to_list()]
        names = [n or "" for n in df[name_col].to_list()]

        # unique texts go to one embed call for efficiency.
        unique: List[str] = list(dict.fromkeys([*queries, *names]))
        embeddings = np.asarray(self.embedder.embed(unique), dtype=np.float64)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(unique):
            raise ValueError(
                f"Embedder must return (n, dim); got shape {getattr(embeddings, 'shape', None)}"
            )
        by_text = {t: embeddings[i] for i, t in enumerate(unique)}

        scores = [
            cosine_similarity(by_text[q], by_text[n]) 
            for q, n in zip(queries, names, strict=True)
        ]
        out = df.with_columns(
            pl.Series(CandidateColumns.SEMANTIC_SCORE, scores, dtype=pl.Float64)
        ).filter(pl.col(CandidateColumns.SEMANTIC_SCORE) >= self.threshold)
        return CandidateTable.enforce_schema(out)