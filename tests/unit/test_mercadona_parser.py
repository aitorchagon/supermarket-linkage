from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from supermarket_linkage.catalog.catalog_client_factory import CatalogClientFactory
from supermarket_linkage.catalog.mercadona_client import (
    MercadonaCatalogClient,
    hits_to_product_table,
    index_name_for,
    parse_hit,
    parse_product_detail,
    sanitize_warehouse,
)
from supermarket_linkage.consts import (
    DEFAULT_WAREHOUSE,
    MERCADONA_ALGOLIA_HOST,
    MERCADONA_ALGOLIA_QUERIES_PATH,
    MERCADONA_API_BASE,
    MERCADONA_POSTAL_CHANGE_PATH,
    MERCADONA_PRODUCT_URL_TEMPLATE,
)
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SEARCH_FIXTURE = FIXTURES / "mercadona_search_response.json"
DETAIL_FIXTURE = FIXTURES / "mercadona_product_detail.json"

_ALGOLIA_URL = f"{MERCADONA_ALGOLIA_HOST}{MERCADONA_ALGOLIA_QUERIES_PATH}"
_POSTAL_URL = f"{MERCADONA_API_BASE}{MERCADONA_POSTAL_CHANGE_PATH}"


def _load_search() -> dict:
    return json.loads(SEARCH_FIXTURE.read_text(encoding="utf-8"))


def _load_detail() -> dict:
    return json.loads(DETAIL_FIXTURE.read_text(encoding="utf-8"))


def test_parse_hit_regular_product() -> None:
    hit = _load_search()["hits"][2]
    row = parse_hit(hit, "arroz")
    assert row[ProductColumns.PRODUCT_ID] == "4245"
    assert row[ProductColumns.NAME] == "Arroz basmati Hacendado Paquete 1 kg"
    assert row[ProductColumns.BRAND] == "Hacendado"
    assert row[ProductColumns.PRICE_EUR] == 1.50
    assert row[ProductColumns.PROMO_PRICE_EUR] is None
    assert row[ProductColumns.UNIT_MEASURE] == "KILO"
    assert row[ProductColumns.SOURCE_QUERY] == "arroz"
    assert row[ProductColumns.URL] == (
        "https://tienda.mercadona.es/product/4245/arroz-basmati-hacendado-paquete"
    )


def test_parse_hit_promo_uses_previous_as_regular() -> None:
    hit = _load_search()["hits"][0]
    row = parse_hit(hit, "leche")
    assert row[ProductColumns.PRODUCT_ID] == "30902"
    assert row[ProductColumns.PRICE_EUR] == 0.84
    assert row[ProductColumns.PROMO_PRICE_EUR] == 0.75
    assert row[ProductColumns.UNIT_MEASURE] == "LITRO"


def test_parse_hit_unidad_without_weight() -> None:
    hit = _load_search()["hits"][3]
    row = parse_hit(hit, "estropajo")
    assert row[ProductColumns.PRODUCT_ID] == "88001"
    assert row[ProductColumns.UNIT_MEASURE] == "UNIDAD"
    assert row[ProductColumns.PRICE_EUR] == 0.80
    assert row[ProductColumns.PROMO_PRICE_EUR] is None


def test_hits_to_product_table_enforces_schema() -> None:
    hits = _load_search()["hits"]
    df = hits_to_product_table(hits, "leche")
    assert df.columns == ProductTable.columns()
    assert df.height == 4
    leche = df.filter(pl.col(ProductColumns.PRODUCT_ID) == "30902").row(0, named=True)
    assert leche[ProductColumns.PRICE_PER_KG] == pytest.approx(0.75)
    arroz = df.filter(pl.col(ProductColumns.PRODUCT_ID) == "4245").row(0, named=True)
    assert arroz[ProductColumns.APPROX_WEIGHT_KG] == pytest.approx(1.0)
    assert arroz[ProductColumns.PRICE_PER_KG] == pytest.approx(1.50)
    unid = df.filter(pl.col(ProductColumns.PRODUCT_ID) == "88001").row(0, named=True)
    assert unid[ProductColumns.PRICE_PER_KG] is None


def test_empty_hits_empty_table() -> None:
    df = hits_to_product_table([], "nada")
    assert df.height == 0
    assert df.columns == ProductTable.columns()


def test_parse_product_detail() -> None:
    detail = _load_detail()
    row = parse_product_detail(detail, "atun")
    assert row[ProductColumns.PRODUCT_ID] == "41001"
    assert row[ProductColumns.PRICE_EUR] == 3.45
    assert row[ProductColumns.PROMO_PRICE_EUR] == 2.90
    assert row[ProductColumns.UNIT_MEASURE] == "KILO"
    assert row[ProductColumns.APPROX_WEIGHT_KG] == pytest.approx(0.24)
    assert row[ProductColumns.SOURCE_QUERY] == "atun"


def test_sanitize_warehouse() -> None:
    assert sanitize_warehouse("MAD1") == "mad1"
    assert sanitize_warehouse("vlc1") == "vlc1"
    assert sanitize_warehouse("https://evil.example") is None
    assert sanitize_warehouse("mad1/../../x") is None
    assert sanitize_warehouse("mad 1") is None
    assert index_name_for("mad1") == "products_prod_mad1_es"
    assert index_name_for("https://evil") == f"products_prod_{DEFAULT_WAREHOUSE}_es"


def test_share_url_rejects_foreign_host() -> None:
    hit = {
        "id": "1",
        "display_name": "X",
        "share_url": "https://evil.example/product/1",
        "price_instructions": {"unit_price": "1.00", "reference_format": "ud"},
    }
    row = parse_hit(hit, "x")
    assert row[ProductColumns.URL] == MERCADONA_PRODUCT_URL_TEMPLATE.format(product_id="1")


def test_search_batch_uses_fixture_via_httpx(httpx_mock) -> None:
    payload = _load_search()
    arroz_hits = [h for h in payload["hits"] if h["id"] == "4245"]
    leche_hits = [h for h in payload["hits"] if h["id"] in {"30902", "30903"}]
    httpx_mock.add_response(
        method="POST",
        url=_ALGOLIA_URL,
        json={
            "results": [
                {"hits": leche_hits, "query": "leche"},
                {"hits": arroz_hits, "query": "arroz"},
            ]
        },
    )
    client = MercadonaCatalogClient(warehouse="mad1", sleep_s=0)
    df = client.search_batch(["leche", "arroz"])
    assert df.height == 3
    queries = set(df[ProductColumns.SOURCE_QUERY].to_list())
    assert queries == {"leche", "arroz"}
    request = httpx_mock.get_request()
    assert str(request.url) == _ALGOLIA_URL
    assert request.url.host == "7uzjkl1dj0-dsn.algolia.net"
    body = json.loads(request.content.decode("utf-8"))
    assert body["requests"][0]["indexName"] == "products_prod_mad1_es"


def test_search_empty_queries() -> None:
    client = MercadonaCatalogClient(warehouse="mad1", sleep_s=0)
    df = client.search_batch(["", "  "])
    assert df.height == 0


def test_postal_to_warehouse_from_header(httpx_mock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=_POSTAL_URL,
        json={},
        headers={"x-customer-wh": "vlc1", "x-customer-pc": "46001"},
    )
    client = MercadonaCatalogClient(sleep_s=0)
    assert client.resolve_warehouse("46001") == "vlc1"
    request = httpx_mock.get_request()
    assert str(request.url) == _POSTAL_URL
    assert json.loads(request.content.decode("utf-8")) == {"new_postal_code": "46001"}


def test_invalid_postal_skips_http(httpx_mock) -> None:
    client = MercadonaCatalogClient(sleep_s=0)
    assert client.resolve_warehouse("not-a-cp") == DEFAULT_WAREHOUSE
    assert client.resolve_warehouse("http://evil") == DEFAULT_WAREHOUSE
    assert httpx_mock.get_requests() == []


def test_ctor_warehouse_skips_postal_lookup(httpx_mock) -> None:
    client = MercadonaCatalogClient(warehouse="bcn1", sleep_s=0)
    assert client.resolve_warehouse() == "bcn1"
    assert httpx_mock.get_requests() == []


def test_factory_mercadona_enabled() -> None:
    client = CatalogClientFactory.get("Mercadona", warehouse="mad1", sleep_s=0)
    assert isinstance(client, MercadonaCatalogClient)


def test_factory_dia_stub_raises() -> None:
    client = CatalogClientFactory.get("dia")
    with pytest.raises(NotImplementedError, match="DIA"):
        client.search("leche")
    with pytest.raises(NotImplementedError, match="DIA"):
        client.search_batch(["leche"])


def test_factory_carrefour_stub_raises() -> None:
    client = CatalogClientFactory.get("carrefour")
    with pytest.raises(NotImplementedError, match="Carrefour"):
        client.search("leche")


def test_factory_unknown_store() -> None:
    with pytest.raises(ValueError, match="Unknown store"):
        CatalogClientFactory.get("aldi")
