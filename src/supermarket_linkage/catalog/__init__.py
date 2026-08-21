"""Catalog clients and promo policies."""

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
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


def __getattr__(name: str):
    # Lazy imports avoid circular deps (mercadona → price_normalizer → catalog package).
    if name == "CarrefourCatalogClient":
        from supermarket_linkage.catalog.carrefour_client import CarrefourCatalogClient

        return CarrefourCatalogClient
    if name == "CatalogClientFactory":
        from supermarket_linkage.catalog.catalog_client_factory import CatalogClientFactory

        return CatalogClientFactory
    if name == "DiaCatalogClient":
        from supermarket_linkage.catalog.dia_client import DiaCatalogClient

        return DiaCatalogClient
    if name == "MercadonaCatalogClient":
        from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient

        return MercadonaCatalogClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
