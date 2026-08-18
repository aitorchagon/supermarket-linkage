"""Embedding-model registry: lifespan preload, with lazy-load fallback.

Warm worker = process up + embedder loaded (DESIGN.md §10).

- Production: ``SentenceTransformerEmbedder`` (``EMBEDDING_MODEL_NAME``).
  ``lifespan`` calls ``preload()``. If that is skipped or fails, ``get()``
  lazy-loads on first ``/warmup`` or job (first request pays cold-start).
- ``USE_SAMPLE_CATALOG=1``: ``TokenOverlapEmbedder`` (no MiniLM download).
  Tests inject an ``Embedder`` and set ``skip_model_preload``.
"""

from __future__ import annotations

import threading
from typing import Literal, Sequence

import numpy as np

from supermarket_linkage.consts import EMBEDDING_MODEL_NAME
from supermarket_linkage.pipeline.semantic_stage import Embedder

_SKIP_TOKENS: frozenSet[str] = frozenset(
    {"kg", "g", "l", "ml", "cl", "uds", "ud", "x", "pack", "packs"}
)

Backend = Literal["sentence-transformers", "sample"]


class TokenOverlapEmbedder:
    """Bag-of-alpha-tokens; CI/sample-safe (no downloads)."""

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        for text in texts:
            for tok in _tokens(text):
                if tok not in self._vocab:
                    self._vocab[tok] = len(self._vocab)
        dim = max(len(self._vocab), 1)
        out = np.zeros((len(texts), dim), dtype=np.float64)
        for i, text in enumerate(texts):
            for tok in _tokens(text):
                out[i, self._vocab[tok]] = 1.0
        return out


class SentenceTransformerEmbedder:
    """Lazy wrapper around ``sentence_transformers.SentenceTransformer``."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if self._model is None:
            self.load()
        encoded = self._model.encode(list(texts), convert_to_numpy=True)  # type: ignore[union-attr]
        return np.asarray(encoded, dtype=np.float64)


class ModelRegistry:
    """Process-wide embedder. Thread-safe load-once."""

    def __init__(
        self,
        *,
        backend: Backend = "sentence-transformers",
        embedder: Embedder | None = None,
    ) -> None:
        self.backend = backend
        self._embedder: Embedder | None = embedder
        self._lock = threading.Lock()
        self.last_error: str | None = None

    @property
    def warm(self) -> bool:
        return self._embedder is not None

    def preload(self) -> Embedder:
        """Load the configured backend if not already loaded."""
        return self.get()

    def get(self) -> Embedder:
        """Return the embedder, lazy-loading if lifespan did not preload.

        Pre: none.
        Post: a usable ``Embedder``; ``warm`` is True.
        """
        with self._lock:
            if self._embedder is not None:
                return self._embedder
            try:
                self._embedder = _build_embedder(self.backend)
                self.last_error = None
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: model load failed"
                raise
            return self._embedder


def _build_embedder(backend: Backend) -> Embedder:
    if backend == "sample":
        return TokenOverlapEmbedder()
    st = SentenceTransformerEmbedder()
    st.load()
    return st


def _tokens(text: str) -> List[str]:
    return [t for t in (text or "").split() if t.isalpha() and t not in _SKIP_TOKENS]
