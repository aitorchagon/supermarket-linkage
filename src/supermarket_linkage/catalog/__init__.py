"""Catalog clients and promo policies."""

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.catalog.carrefour_client import CarrefourCatalogClient
from supermarket_linkage.catalog.catalog_client_factory import CatalogClientFactory
from supermarket_linkage.catalog.dia_client import DiaCatalogClient
from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient
from supermarket_linkage.catalog.promo_policy import MercadonaPromoPolicy, PromoPolicy

__all__ = [
    "BaseCatalogClient",
    "CarrefourCatalogClient",
    "CatalogClientFactory",
    "DiaCatalogClient",
    "MercadonaCatalogClient",
    "MercadonaPromoPolicy",
    "PromoPolicy",
]
