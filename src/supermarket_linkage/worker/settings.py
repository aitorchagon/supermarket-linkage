"""Worker process settings from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from supermarket_linkage.consts import JOB_TIMEOUT_SECONDS, JOB_TTL_SECONDS


def env_flag(name: str) -> bool:
    """True when ``name`` is a truthy env flag (1/true/yes/on)."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkerSettings:
    """Runtime flags for the FastAPI worker.

    ``use_sample_catalog``: local/CI path — no Mercadona HTTP, TokenOverlap embedder.
    ``skip_model_preload``: skip lifespan ``preload()`` (tests). Lazy-load still works.
    """

    api_key: str | None
    use_sample_catalog: bool
    skip_model_preload: bool
    sample_catalog_path: str | None
    job_timeout_s: int = JOB_TIMEOUT_SECONDS
    job_ttl_s: int = JOB_TTL_SECONDS

    @classmethod
    def from_env(cls) -> WorkerSettings:
        key = os.environ.get("WORKER_API_KEY", "").strip() or None
        sample = env_flag("USE_SAMPLE_CATALOG")
        # MiniLM is skipped by using the sample backend; TokenOverlap still
        # preloads in lifespan unless SKIP_MODEL_PRELOAD=1 (tests).
        skip_preload = env_flag("SKIP_MODEL_PRELOAD")
        path = os.environ.get("SAMPLE_CATALOG_PATH", "").strip() or None
        return cls(
            api_key=key,
            use_sample_catalog=sample,
            skip_model_preload=skip_preload,
            sample_catalog_path=path,
        )
