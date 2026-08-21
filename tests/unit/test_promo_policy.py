from supermarket_linkage.catalog.promo_policy import MercadonaPromoPolicy
from supermarket_linkage.schemas.product_table import ProductColumns

_POLICY = MercadonaPromoPolicy()


def test_member_uses_promo_price() -> None:
    row = {ProductColumns.PRICE_EUR: 0.84, ProductColumns.PROMO_PRICE_EUR: 0.75}
    assert _POLICY.effective_price(row, is_promo_member=True) == 0.75


def test_non_member_ignores_promo_price() -> None:
    row = {ProductColumns.PRICE_EUR: 0.84, ProductColumns.PROMO_PRICE_EUR: 0.75}
    assert _POLICY.effective_price(row, is_promo_member=False) == 0.84


def test_member_without_promo_uses_regular() -> None:
    row = {ProductColumns.PRICE_EUR: 1.50, ProductColumns.PROMO_PRICE_EUR: None}
    assert _POLICY.effective_price(row, is_promo_member=True) == 1.50


def test_missing_regular_and_promo_is_none() -> None:
    row = {ProductColumns.PRICE_EUR: None, ProductColumns.PROMO_PRICE_EUR: None}
    assert _POLICY.effective_price(row, is_promo_member=True) is None
    assert _POLICY.effective_price(row, is_promo_member=False) is None


def test_member_promo_only_when_promo_present() -> None:
    row = {ProductColumns.PRICE_EUR: None, ProductColumns.PROMO_PRICE_EUR: 2.90}
    assert _POLICY.effective_price(row, is_promo_member=True) == 2.90
    assert _POLICY.effective_price(row, is_promo_member=False) is None
