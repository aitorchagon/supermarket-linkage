"""Store → catalog client. Mercadona enabled; DIA / Carrefour stubbed."""

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.catalog.carrefour_client import CarrefourCatalogClient
from supermarket_linkage.catalog.dia_client import DiaCatalogClient
from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient
from supermarket_linkage.consts import COMING_SOON_STORES, SUPPORTED_STORES

_CLIENTS: dict[str, type[BaseCatalogClient]] = {
    "mercadona": MercadonaCatalogClient,
    "dia": DiaCatalogClient,
    "carrefour": CarrefourCatalogClient,
}


class CatalogClientFactory:
    """Return a catalog client for a store id (lowercase)."""

    @staticmethod
    def get(store: str, **kwargs: object) -> BaseCatalogClient:
        """Instantiate the client for ``store``.

        Pre: ``store`` is a user/UI store id (any case).
        Post: Mercadona client is usable; DIA/Carrefour raise on search.
        """
        key = store.strip().lower()
        cls = _CLIENTS.get(key)
        if cls is None:
            known = (*SUPPORTED_STORES, *COMING_SOON_STORES)
            raise ValueError(f"Unknown store {store!r}. Known: {known}")
        return cls(**kwargs)  # type: ignore[arg-type]
