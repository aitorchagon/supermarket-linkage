from typing import (
    FrozenSet,
    Literal,
)

SECONDS_PER_HOUR = 3600.0
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_SEARCHING = "searching"
STATUS_LINKING = "linking"
API_KEY_HEADERS = ("x-api-key", "worker-api-key", "worker_api_key")
_SKIP_TOKENS: FrozenSet[str] = frozenset(
    {"kg", "g", "l", "ml", "cl", "uds", "ud", "x", "pack", "packs"}
)
Backend = Literal["sentence-transformers", "sample"]