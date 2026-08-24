from __future__ import annotations

import threading
from typing import (
    Sequence,
    Dict,
    Optional, 
    Any,
    List,
)

import numpy as np
from numpy.typing import NDArray

from supermarket_linkage.consts import EMBEDDING_MODEL_NAME
from supermarket_linkage.pipeline.semantic_stage import Embedder
from supermarket_linkage.worker.consts import (
    _SKIP_TOKENS,
    Backend,
)

class TokenOverlapEmbedder:
    """
    This is a bag of tokens, it does not download any model.
    """

    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
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
    """
    This is a lazy wrapper around sentence_transformers.SentenceTransformer.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model: Optional[Any] = None

    def load(self) -> None:
        # we use the import here to avoid loading weights on CPU/GPU if it is not necessary.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if self._model is None:
            self.load()
        encoded = self._model.encode(list(texts), convert_to_numpy=True)  # type: ignore[union-attr]
        return np.asarray(encoded, dtype=np.float64)


class ModelRegistry:
    """
    This is a process-wide embedder, to be loaded-once. 
    """

    def __init__(
        self,
        *,
        backend: Backend = "sentence-transformers",
        embedder: Optional[Embedder] = None,
    ) -> None:
        self.backend = backend
        self._embedder: Optional[Embedder] = embedder
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None

    @property
    def warm(self) -> bool:
        return self._embedder is not None

    def preload(self) -> Embedder:
        """
        This function allows to load the configured backend if it is not
        already loaded. 
        """
        return self.get()

    def get(self) -> Embedder:
        """
        This is a getter for the embedder. Provides lazy-loading if lifespan did not
        preload. Provides a usable Embedder, warm is True.
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
    return [
        t
        for t in (text or "").lower().split()
        if t.isalpha() and t not in _SKIP_TOKENS
    ]
