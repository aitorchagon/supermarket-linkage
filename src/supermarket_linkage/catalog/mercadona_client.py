"""
Mercadona catalog client: Algolia search (to retrieve data) + postal→warehouse (hardcoded hosts).
"""

from __future__ import annotations

import time
from typing import (
    Any, 
    Self, 
    Optional,
    Tuple,
    Dict,
    Mapping,
    Sequence,
)
from urllib.parse import urlencode

import httpx
import polars as pl

from supermarket_linkage.catalog.base_catalog_client import BaseCatalogClient
from supermarket_linkage.consts import (
    DEFAULT_WAREHOUSE,
    HTTP_RATE_LIMIT_SECONDS,
    MERCADONA_HITS_PER_PAGE,
    MERCADONA_INDEX_TEMPLATE,
    MERCADONA_PRODUCT_URL_PREFIX,
    MERCADONA_PRODUCT_URL_TEMPLATE,
    MERCADONA_SEARCH_BATCH_SIZE,
)
from supermarket_linkage.catalog.consts import (
    _ALGOLIA_URL,
    _POSTAL_URL,
    _ALGOLIA_HEADERS,
    _WH_HEADER,
)
from supermarket_linkage.preprocessors.price_normalizer import (
    PriceNormalizer,
    canonicalize_unit_measure,
)
from supermarket_linkage.preprocessors.units import to_kg

from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.validation.postal_code_validator import is_valid_postal_code
from supermarket_linkage.catalog.utils import (
    _to_float,
    sanitize_warehouse,
)

def _unit_measure(price_instructions: Mapping[str, Any]) -> Optional[str]:
    """
    This function allows to canonicalize unit measures for the product, so we can compare
    products in an uniform way.
    """
    raw = price_instructions.get("reference_format") or price_instructions.get("size_format")
    if raw is None:
        return None
    return canonicalize_unit_measure(str(raw))


def _approx_weight_kg(price_instructions: Mapping[str, Any]) -> Optional[float]:
    """
    This function allows to obtain the approximated weight of a product and normalize it to 
    kilograms.
    """
    size = _to_float(price_instructions.get("unit_size"))
    fmt = price_instructions.get("size_format")
    if size is None or not fmt:
        return None
    return to_kg(size, str(fmt))

def _get_prices(
        price_instructions: Mapping[str, Any]
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    This function allows to return a regular pack price plus a promo pack price (only when
    price decreased) measured in euros.
    """
    current = _to_float(price_instructions.get("unit_price"))
    previous = _to_float(price_instructions.get("previous_unit_price"))
    decreased = bool(price_instructions.get("price_decreased"))
    unit_price = _to_float(price_instructions.get("reference_price"))
    if decreased and previous is not None and current is not None:
        return previous, current, unit_price
    # we do not have a previous pack price for the product
    return current, None, unit_price

def get_algolia_index(warehouse: str) -> str:
    """
    This function is a getter for the Algolia index, using a sanitized warehouse for Mercadona. 
    """
    safe = sanitize_warehouse(warehouse) or DEFAULT_WAREHOUSE
    return MERCADONA_INDEX_TEMPLATE.format(warehouse=safe)


def _product_url(hit: Mapping[str, Any], product_id: str) -> str:
    """
    This function allows to get a product URL to be provided to the final user.
    """
    share = hit.get("share_url")
    if isinstance(share, str) and share.startswith(MERCADONA_PRODUCT_URL_PREFIX):
        return share
    return MERCADONA_PRODUCT_URL_TEMPLATE.format(product_id=product_id)


def _display_name(hit: Mapping[str, Any]) -> str:
    """
    This function allows to get the display name of the product to be provided to the final user.
    """
    # display_name or name or nothing if we do not have a display name for a product
    name = str(hit.get("display_name") or hit.get("name") or "").strip()
    packaging = str(hit.get("packaging") or "").strip()
    if name and packaging and packaging.lower() not in name.lower():
        return f"{name} {packaging}"
    return name


def parse_hit(hit: Mapping[str, Any], source_query: str) -> Dict[str, Any]:
    """
    This function allows to parse Algolia hits (one) or JSON objects to a ProductTable row.

    Arguments
    ---------
    hit: This is a dictionary that map a string (hit) to a product (undefined type).
    source_query: This is the source query that was used.

    Returns
    --------
    A dictionary that contains all the data in a ProductTable format.
    """
    product_id = str(hit.get("id") or hit.get("objectID") or "")
    price_instructions = hit.get("price_instructions") or {}
    if not isinstance(price_instructions, Mapping):
        price_instructions = {}
    price_eur, promo_price_eur, unit_price_eur = _get_prices(
        price_instructions=price_instructions
    )
    return {
        ProductColumns.PRODUCT_ID: product_id or None,
        ProductColumns.NAME: _display_name(hit=hit) or None,
        ProductColumns.BRAND: (str(hit["brand"]) if hit.get("brand") else None),
        ProductColumns.PRICE_EUR: price_eur,
        ProductColumns.PROMO_PRICE_EUR: promo_price_eur,
        ProductColumns.UNIT_PRICE_EUR: _to_float(value=unit_price_eur),
        ProductColumns.UNIT_MEASURE: _unit_measure(price_instructions=price_instructions),
        ProductColumns.APPROX_WEIGHT_KG: _approx_weight_kg(price_instructions=price_instructions),
        ProductColumns.PRICE_PER_KG: None,
        ProductColumns.SOURCE_QUERY: source_query,
        ProductColumns.URL: _product_url(hit=hit, product_id=product_id) if product_id else None,
    }

def hits_to_product_table(
    hits: Sequence[Mapping[str, Any]],
    source_query: str,
) -> pl.DataFrame:
    """
    This function allows to parse a list of hits into a ProductTable (with price/kg filled).

    Arguments
    ---------
    hits: This is a list of dictionaries that map a string (hit) to a product (undefined type).
    source_query: This is the source query that was used.

    Returns
    --------
    A table that contains all the data with the prices normalized.
    """
    if not hits:
        return ProductTable.as_empty_dataframe()
    rows = [parse_hit(hit, source_query) for hit in hits]
    df = ProductTable.enforce_schema(pl.DataFrame(rows))
    return PriceNormalizer().process(df)


class MercadonaCatalogClient(BaseCatalogClient):
    """
    This is a httpx client for Mercadona Algolia search. Hosts are compile-time constants.
    """

    def __init__(
        self,
        *,
        postal_code: Optional[str] = None,
        warehouse: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        sleep_s: float = HTTP_RATE_LIMIT_SECONDS,
        hits_per_page: int = MERCADONA_HITS_PER_PAGE,
    ) -> None:
        self._postal_code = postal_code
        self._warehouse = sanitize_warehouse(warehouse) or DEFAULT_WAREHOUSE
        self._warehouse_from_ctor = sanitize_warehouse(warehouse) is not None
        self._sleep_s = sleep_s
        self._hits_per_page = hits_per_page
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=20.0)
        self._warehouse_cache: Dict[str, str] = {}

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def search_batch(
        self,
        query: str,
        *,
        postal_code: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        This function allows to search a batch of products. To do that, it 
        performs a POST Algolia multi-query in chunks of ``MERCADONA_SEARCH_BATCH_SIZE``.

        Arguments
        --------
        queries: It is a list of search strings, where empty ones are skipped.
        postal_code: It may or may not be included, allows to search in particular stores.

        Returns
        -------
        A concatenated ProductTable where each source_query matches each input query.
        """
        queries = [query]
        cleaned = [q for q in queries if q and q.strip()]
        if not cleaned:
            return ProductTable.as_empty_dataframe()

        warehouse = self.resolve_warehouse(postal_code)
        index = get_algolia_index(warehouse)
        frames: List[pl.DataFrame] = []
        for start in range(0, len(cleaned), MERCADONA_SEARCH_BATCH_SIZE):
            chunk = cleaned[start : start + MERCADONA_SEARCH_BATCH_SIZE]
            payload = {
                "requests": [
                    {
                        "indexName": index,
                        "params": urlencode(
                            {"query": q, "hitsPerPage": self._hits_per_page}
                        ),
                    }
                    for q in chunk
                ]
            }
            response = self._request("POST", _ALGOLIA_URL, headers=_ALGOLIA_HEADERS, json=payload)
            response.raise_for_status()
            body = response.json()
            results = body.get("results") or []
            for query, result in zip(chunk, results, strict=False):
                hits = result.get("hits") or [] if isinstance(result, Mapping) else []
                frames.append(hits_to_product_table(hits, query))

        if not frames:
            return ProductTable.as_empty_dataframe()
        return ProductTable.enforce_schema(pl.concat(frames, how="diagonal"))

    def resolve_warehouse(self, postal_code: Optional[str] = None) -> str:
        """
        This function allows to map a Spanish postal_code, if provided, to a warehouse
        . We provide the default one if unknown.

        Arguments
        ---------
        postal_code: This is the postal code that the user specified, or None if it was not specified.

        Returns
        ---------
        resolved: A sanitized warehouse code
        """
        if self._warehouse_from_ctor and postal_code is None:
            return self._warehouse

        code = postal_code if postal_code is not None else self._postal_code
        if not code:
            return self._warehouse
        if code in self._warehouse_cache:
            return self._warehouse_cache[code]
        if not is_valid_postal_code(code):
            return self._warehouse

        resolved = self._lookup_warehouse(code) or self._warehouse
        self._warehouse_cache[code] = resolved
        return resolved

    def _lookup_warehouse(self, postal_code: str) -> Optional[str]:
        """
        This function allows to lookup a warehouse using a provided postal code.
        To do that, it performs a PUT against the _POSTAL_URL specified in the constants; if it is not
        found, we return None. Otherwise, we provided a sanitized warehouse code.
        """
        response = self._request(
            "PUT",
            _POSTAL_URL,
            headers={"content-type": "application/json"},
            json={"new_postal_code": postal_code},
        )
        if response.status_code >= 400:
            return None
        header_wh = sanitize_warehouse(response.headers.get(_WH_HEADER))
        if header_wh:
            return header_wh
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, Mapping):
            return None
        return sanitize_warehouse(
            body.get("warehouse") or body.get("wh") or body.get("customer_wh")
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http.request(method, url, **kwargs)
        finally:
            if self._sleep_s > 0:
                time.sleep(self._sleep_s)
