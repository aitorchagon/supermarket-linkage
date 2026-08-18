from supermarket_linkage.catalog.carrefour_client import CarrefourCatalogClient
from supermarket_linkage.catalog.dia_client import DiaCatalogClient
from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient
from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
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

_CLIENTS: dict[str, type[BaseCatalogClient]] = {
    "mercadona": MercadonaCatalogClient,
    "dia": DiaCatalogClient,
    "carrefour": CarrefourCatalogClient,
}

_ALGOLIA_URL = f"{MERCADONA_ALGOLIA_HOST}{MERCADONA_ALGOLIA_QUERIES_PATH}"
_POSTAL_URL = f"{MERCADONA_API_BASE}{MERCADONA_POSTAL_CHANGE_PATH}"
_ALGOLIA_HEADERS = {
    "x-algolia-application-id": MERCADONA_ALGOLIA_APP_ID,
    "x-algolia-api-key": MERCADONA_ALGOLIA_API_KEY,
    "content-type": "application/json",
}
_WH_HEADER = "x-customer-wh"