from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Optional

from supermarket_linkage.schemas.product_table import ProductColumns
from supermarket_linkage.catalog.utils import _to_float

class PromoPolicy(ABC):
    """
    This class picks the unit price the shopper pays.
    """

    @abstractmethod
    def effective_price(self, row: Mapping[str, Any], is_promo_member: bool) -> Optional[float]:
        """
        This function allows to return the payable pack price for one product row.

        Arguments
        ---------
        row: This is a dictionary that contains a relation between price_eur/promo_price_eur and the product.
        is_promo_member: This is a boolean that allows to establish whether the person is a promo member.

        Returns
        --------
        The payable pack price for a product.
        """


class MercadonaPromoPolicy(PromoPolicy):
    """Use Mercadona promo/sale price only when the shopper opts into promos."""

    def effective_price(self, row: Mapping[str, Any], is_promo_member: bool) -> float | None:
        """Member + promo field → promo; otherwise regular ``price_eur``.

        Pre: ``row`` is a product/candidate mapping.
        Post: float or None; never returns promo when ``is_promo_member`` is False.
        """
        regular = _to_float(row.get(ProductColumns.PRICE_EUR))
        promo = _to_float(row.get(ProductColumns.PROMO_PRICE_EUR))
        if is_promo_member and promo is not None:
            return promo
        return regular


class CarrefourPromoPolicy(PromoPolicy):
    def effective_price(self, row, is_promo_member):
        raise NotImplementedError

class DIAPromoPolicy(PromoPolicy):
    def effective_price(self, row, is_promo_member):
        raise NotImplementedError