from typing import Optional
import httpx

class WorkerError(Exception):
    """
    This error is raised when the worker is unreachable or when it returned an error.
    We make sure the worker error never includes pasted text by the client.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code

def _error_message(response: httpx.Response) -> str:
    """
    This function allows to configure an error message for different situations
    according to the status code of the petition we are performing against the API.
    """
    detail: str | None = None
    try:
        body = response.json()
        raw = body.get("detail") if isinstance(body, dict) else None
        if isinstance(raw, str):
            detail = raw
        elif raw is not None:
            detail = str(raw)
    except (ValueError, TypeError):
        detail = None
    if response.status_code == 401:
        return "Clave de API inválida o ausente."
    if response.status_code == 429:
        return (
            "Demasiadas búsquedas en poco tiempo. Espera un minuto e inténtalo de nuevo."
        )
    if response.status_code == 404:
        return (
            "Ese resultado ya no está disponible (el servidor se reinició o pasó demasiado "
            "tiempo). Pulsa Emparejar otra vez."
        )
    if detail:
        # Map worker jargon to Spanish UX copy when possible.
        low = detail.lower()
        if "rate limit" in low:
            return (
                "Demasiadas búsquedas en poco tiempo. Espera un minuto e inténtalo de nuevo."
            )
        if "job not found" in low:
            return (
                "Ese resultado ya no está disponible. Pulsa Emparejar otra vez."
            )
        return detail
    return f"Error del worker (HTTP {response.status_code})."