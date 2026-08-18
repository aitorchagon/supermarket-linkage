"""Opt-in live Mercadona Algolia smoke. Skipped unless RUN_LIVE_MERCADONA=1.

One small search only (warehouse ``mad1``, no postal lookup). The client still
applies ``HTTP_RATE_LIMIT_SECONDS`` after the request. Do not loop this test
against Algolia; it is not part of the default suite.

Run once:

    RUN_LIVE_MERCADONA=1 .venv/bin/pytest tests/integration/test_mercadona_live_smoke.py -s -v
"""

from __future__ import annotations

import os

import pytest

from supermarket_linkage.catalog.mercadona_client import MercadonaCatalogClient
from supermarket_linkage.consts import MERCADONA_PRODUCT_URL_PREFIX
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_MERCADONA") != "1",
        reason="opt-in live Mercadona; set RUN_LIVE_MERCADONA=1",
    ),
]

_QUERY = "arroz"
_HITS_PER_PAGE = 5


def test_live_one_small_search() -> None:
    """Single Algolia query. Failures are the smoke result — do not retry in a loop."""
    with MercadonaCatalogClient(warehouse="mad1", hits_per_page=_HITS_PER_PAGE) as client:
        df = client.search(_QUERY)

    assert df.columns == ProductTable.columns()
    assert df.height >= 1, "expected at least one hit for 'arroz'"
    ids = [x for x in df[ProductColumns.PRODUCT_ID].to_list() if x]
    names = [x for x in df[ProductColumns.NAME].to_list() if x]
    urls = [x for x in df[ProductColumns.URL].to_list() if x]
    assert ids, "parser produced no product_id (live JSON shape may have changed)"
    assert names, "parser produced no name (live JSON shape may have changed)"
    assert urls, "parser produced no url"
    assert all(u.startswith(MERCADONA_PRODUCT_URL_PREFIX) for u in urls)
    assert all(q == _QUERY for q in df[ProductColumns.SOURCE_QUERY].to_list())
    first = df.row(0, named=True)
    print(
        f"live smoke ok: hits={df.height} "
        f"id={first[ProductColumns.PRODUCT_ID]!r} "
        f"name={first[ProductColumns.NAME]!r}"
    )
