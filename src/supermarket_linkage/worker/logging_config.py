from __future__ import annotations

from typing import Optional
import logging
import os


_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configure root logging once for the worker process.
    """
    raw = (level or os.environ.get("LOG_LEVEL", "INFO")).strip().upper() or "INFO"
    numeric = getattr(logging, raw, None)
    if not isinstance(numeric, int):
        numeric = logging.INFO
    logging.basicConfig(
        level=numeric,
        format=_DEFAULT_FORMAT,
        datefmt=_DEFAULT_DATEFMT,
        force=True,
    )
