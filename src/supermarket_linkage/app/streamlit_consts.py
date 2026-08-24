from typing import (
    Dict,
    Tuple,

)
import threading

from supermarket_linkage.consts import (
    COMING_SOON_STORES,
    SUPPORTED_STORES,
)
from supermarket_linkage.export.mercadona_export_builder import MercadonaExportBuilder
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.validation.input_validator import InputValidator

_WARMUP_LOCK = threading.Lock()
_WARMUP_IN_FLIGHT = False
_WARMUP_DONE = False
_LAST_WARMUP_ATTEMPT = 0.0
_WARMUP_RETRY_S = 15.0
_WARMUP_TIMEOUT_S = 90.0

_HEALTH_TIMEOUT_S = 5.0
_JOB_TIMEOUT_S = 30.0
_POLL_TIMEOUT_S = 15.0

_STORE_LABELS: Dict[str, str] = {
    "mercadona": "Mercadona",
    "dia": "DIA (Próximamente)",
    "carrefour": "Carrefour (Próximamente)",
}
_STORE_ORDER: Tuple[str] = (*SUPPORTED_STORES, *COMING_SOON_STORES)

_PROGRESS_LABELS: Dict[str, str] = {
    "queued": "en cola",
    "running": "en curso",
    "searching": "buscando catálogo",
    "linking": "emparejando",
    "done": "listo",
    "error": "error",
    "timeout": "tiempo agotado",
}

_RESULT_COLUMNS: Tuple[str] = (
    LineResultColumns.QUERY,
    LineResultColumns.STATUS,
    LineResultColumns.NAME,
    LineResultColumns.BRAND,
    LineResultColumns.UNITS_NEEDED,
    LineResultColumns.EFFECTIVE_PRICE_EUR,
    LineResultColumns.LINE_TOTAL_PRICE_EUR,
    LineResultColumns.PRICE_PER_KG,
    LineResultColumns.PACK_SIZE_MISSING,
    LineResultColumns.PRODUCT_URL,
)

_POLL_INTERVAL_S = 0.5
_VALIDATOR = InputValidator()
_EXPORT = MercadonaExportBuilder()
DEFAULT_URL = "http://localhost:8000"