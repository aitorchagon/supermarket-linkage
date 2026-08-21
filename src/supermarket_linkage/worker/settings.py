from __future__ import annotations

import os
from dataclasses import dataclass
from typing import (
    Optional,
)
from supermarket_linkage.consts import (
    JOB_TIMEOUT_SECONDS, 
    JOB_TTL_SECONDS,
)


def env_flag(name: str) -> bool:
    """
    Returns True when name is a true environment flag. 
    """
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkerSettings:
    """
    These are runtime flags for the FastAPI worker.
    """

    api_key: Optional[str]
    use_sample_catalog: bool
    skip_model_preload: bool
    sample_catalog_path: Optional[str]
    job_timeout_s: int = JOB_TIMEOUT_SECONDS
    job_ttl_s: int = JOB_TTL_SECONDS

    @classmethod
    def from_env(cls) -> WorkerSettings:
        key = os.environ.get("WORKER_API_KEY", "").strip() or None
        sample = env_flag("USE_SAMPLE_CATALOG")
        # we skip MiniLM using the sample backend, tokenoverlap preloads in lifespan unless
        # skip_model_preload, which is set in the unitary tests
        skip_preload = env_flag("SKIP_MODEL_PRELOAD")
        path = os.environ.get("SAMPLE_CATALOG_PATH", "").strip() or None
        return cls(
            api_key=key,
            use_sample_catalog=sample,
            skip_model_preload=skip_preload,
            sample_catalog_path=path,
        )