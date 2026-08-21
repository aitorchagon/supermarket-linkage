from typing import Tuple

# --- Record linkage ---
SEMANTIC_THRESHOLD: float = 0.75
JW_MAX_DISTANCE: float = 0.1

# --- Input limits ---
MAX_LINES: int = 100
WARN_LINES: int = 50
MAX_LINE_LENGTH: int = 200
MAX_TOTAL_BYTES: int = 50_000
MIN_LINE_LENGTH: int = 1
MAX_DUPLICATE_RATIO: float = 0.95

# --- Job lifecycle ---
JOB_TIMEOUT_SECONDS: int = 600
JOB_TTL_SECONDS: int = 3600

# --- Rate limits (per client IP, in-process) ---
MAX_WARMUP_PER_HOUR: int = 10
MAX_JOBS_PER_HOUR: int = 5
MAX_CONCURRENT_JOBS_PER_IP: int = 1

# --- Mercadona HTTP hosts and URLs ---
MERCADONA_API_BASE: str = "https://tienda.mercadona.es/api"
MERCADONA_ALGOLIA_APP_ID: str = "7UZJKL1DJ0"
MERCADONA_ALGOLIA_API_KEY: str = "9d8f2e39e90df472b4f2e559a116fe17"
MERCADONA_ALGOLIA_HOST: str = f"https://{MERCADONA_ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
MERCADONA_ALGOLIA_QUERIES_PATH: str = "/1/indexes/*/queries"
MERCADONA_POSTAL_CHANGE_PATH: str = "/postal-codes/actions/change-pc/"
MERCADONA_INDEX_TEMPLATE: str = "products_prod_{warehouse}_es"
MERCADONA_PRODUCT_URL_TEMPLATE: str = "https://tienda.mercadona.es/product/{product_id}"
MERCADONA_PRODUCT_URL_PREFIX: str = "https://tienda.mercadona.es/"
MERCADONA_SEARCH_BATCH_SIZE: int = 100
MERCADONA_HITS_PER_PAGE: int = 20
DEFAULT_WAREHOUSE: str = "mad1"
HTTP_RATE_LIMIT_SECONDS: float = 0.5

# --- Embedding model ---
EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"

# --- Stores (v1: mercadona only enabled) ---
SUPPORTED_STORES: Tuple[str] = ("mercadona",)
COMING_SOON_STORES: Tuple[str] = ("dia", "carrefour")
