from dataclasses import dataclass
from typing import (
    Optional,
    Set,
)
from pathlib import Path
import os

from supermarket_linkage.app.streamlit_consts import (
    DEFAULT_URL
)

@dataclass(frozen=True)
class MasterConfig:
    worker_url: str
    api_key: Optional[str]
    

def load_master_config() -> MasterConfig:
    """
    This function allows to load the master configuration, with the following schema:
    ``WORKER_URL`` / ``WORKER_API_KEY`` building it after .env
    """
    candidates = [Path.cwd() / ".env"]
    try:
        candidates.append(Path(__file__).resolve().parents[3] / ".env")
    except IndexError:
        pass
    seen: Set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key:
                    os.environ.setdefault(key, value)
    url = os.environ.get("WORKER_URL", "").strip() or DEFAULT_URL
    key = os.environ.get("WORKER_API_KEY", "").strip() or None
    return MasterConfig(worker_url=url.rstrip("/"), api_key=key)