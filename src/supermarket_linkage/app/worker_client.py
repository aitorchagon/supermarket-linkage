"""
This is the HTTP client for the Streamlit master → FastAPI worker.

Process-level warmup-once lives here so Streamlit script reruns do not
spam ``POST /warmup`` (rate limit is per master IP).
"""

from __future__ import annotations

from typing import (
    Optional,
    Dict,
)
import threading
import time
from typing import Any
import httpx

from supermarket_linkage.app.streamlit_consts import (
    _WARMUP_LOCK,
    _WARMUP_IN_FLIGHT,
    _WARMUP_DONE,
    _LAST_WARMUP_ATTEMPT,
    _WARMUP_RETRY_S,
    _WARMUP_TIMEOUT_S,
    _HEALTH_TIMEOUT_S,
    _JOB_TIMEOUT_S,
    _POLL_TIMEOUT_S,
)
from supermarket_linkage.app.exceptions import (
    WorkerError,
    _error_message,
)


class WorkerClient:
    """
    This client is a httpx client wrapper.
    """

    def __init__(self, base_url: str, api_key: Optional[str]) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-Key": self.api_key}

    def health_or_none(self) -> Dict[str, Any] | None:
        """
        This function performs a GET against /health or returns an error
        """
        try:
            return self._json("GET", "/health", timeout=_HEALTH_TIMEOUT_S)
        except WorkerError:
            return None

    def warmup(self) -> Dict[str, Any]:
        """
        This function performs a POST /warmup; may take up to ~90 s on a cold worker.
        It allows to accelerate posterior calls.
        """
        return self._json("POST", "/warmup", timeout=_WARMUP_TIMEOUT_S)

    def create_job(
        self,
        text: str,
        *,
        store: str,
        postal_code: Optional[str],
        is_promo_member: bool,
    ) -> Dict[str, Any]:
        """This function performs a POST /jobs."""
        payload = {
            "text": text,
            "store": store,
            "postal_code": postal_code,
            "is_promo_member": is_promo_member,
        }
        return self._json("POST", "/jobs", json=payload, timeout=_JOB_TIMEOUT_S)

    def get_job(self, job_id: str) -> dict[str, Any]:
        """This function performs a GET /jobs/{id}."""
        return self._json("GET", f"/jobs/{job_id}", timeout=_POLL_TIMEOUT_S)

    def _json(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=json,
                timeout=timeout,
            )
        except httpx.ConnectError as exc:
            raise WorkerError(
                f"No se puede conectar al worker ({self.base_url})."
            ) from exc
        except httpx.TimeoutException as exc:
            raise WorkerError("El worker no respondió a tiempo.") from exc
        if response.is_success:
            return response.json()
        # else, that is, if response is unsuccessfully and the error is not a timeout
        # or a connecterror
        raise WorkerError(_error_message(response), response.status_code)


def start_warmup_once(client: WorkerClient) -> None:
    """
    This function allows to execute a ``POST /warmup`` in a daemon thread at most once per process,
    with `_WARMUP_RETRY_S`` retries if the previous attempt failed.
    Streamlit reruns import this module from cache, so the flag survives.
    """
    global _WARMUP_IN_FLIGHT, _LAST_WARMUP_ATTEMPT
    now = time.monotonic()
    with _WARMUP_LOCK:
        if _WARMUP_DONE or _WARMUP_IN_FLIGHT:
            return
        if _LAST_WARMUP_ATTEMPT and now - _LAST_WARMUP_ATTEMPT < _WARMUP_RETRY_S:
            return
        _WARMUP_IN_FLIGHT = True
        _LAST_WARMUP_ATTEMPT = now

    def _run() -> None:
        global _WARMUP_IN_FLIGHT, _WARMUP_DONE
        try:
            client.warmup()
            with _WARMUP_LOCK:
                _WARMUP_DONE = True
        except WorkerError:
            pass
        finally:
            with _WARMUP_LOCK:
                _WARMUP_IN_FLIGHT = False

    threading.Thread(target=_run, daemon=True, name="worker-warmup").start()
