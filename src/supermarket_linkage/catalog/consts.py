"""Catalog-layer constants (URLs, headers, stub messages). No client imports."""

from supermarket_linkage.consts import (
    MERCADONA_ALGOLIA_API_KEY,
    MERCADONA_ALGOLIA_APP_ID,
    MERCADONA_ALGOLIA_HOST,
    MERCADONA_ALGOLIA_QUERIES_PATH,
    MERCADONA_API_BASE,
    MERCADONA_POSTAL_CHANGE_PATH,
)

CARREFOUR_NOT_IMPLEMENTED_MESSAGE = "Carrefour catalog client is not implemented in v1."
DIA_NOT_IMPLEMENTED_MESSAGE = "DIA catalog client is not implemented in v1."

_ALGOLIA_URL = f"{MERCADONA_ALGOLIA_HOST}{MERCADONA_ALGOLIA_QUERIES_PATH}"
_POSTAL_URL = f"{MERCADONA_API_BASE}{MERCADONA_POSTAL_CHANGE_PATH}"
_ALGOLIA_HEADERS = {
    "x-algolia-application-id": MERCADONA_ALGOLIA_APP_ID,
    "x-algolia-api-key": MERCADONA_ALGOLIA_API_KEY,
    "content-type": "application/json",
}
_WH_HEADER = "x-customer-wh"
