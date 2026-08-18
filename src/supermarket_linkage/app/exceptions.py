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
        return "Límite de peticiones del worker (429). Prueba más tarde."
    if response.status_code == 404:
        return "Job no encontrado (¿expiró el TTL?)."
    if detail:
        return detail
    return f"Worker HTTP {response.status_code}."