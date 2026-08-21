from typing import Any, Dict, Type

import polars as pl

from supermarket_linkage.schemas.base import ColumnsEnumBase, TableSchemaBase


class ProductColumns(ColumnsEnumBase):
    PRODUCT_ID = "product_id"
    NAME = "name"
    BRAND = "brand"
    PRICE_EUR = "price_eur"
    PROMO_PRICE_EUR = "promo_price_eur"
    UNIT_PRICE_EUR = "unit_price_eur"
    UNIT_MEASURE = "unit_measure"
    APPROX_WEIGHT_KG = "approx_weight_kg"
    PRICE_PER_KG = "price_per_kg"
    SOURCE_QUERY = "source_query"
    URL = "url"


class ProductTable(TableSchemaBase):
    @classmethod
    def get_columns_enum(cls) -> Type[ColumnsEnumBase]:
        return ProductColumns

    @classmethod
    def dtypes(cls) -> Dict[str, Any]:
        return {
            ProductColumns.PRODUCT_ID: pl.String,
            ProductColumns.NAME: pl.String,
            ProductColumns.BRAND: pl.String,
            ProductColumns.PRICE_EUR: pl.Float64,
            ProductColumns.PROMO_PRICE_EUR: pl.Float64,
            ProductColumns.UNIT_PRICE_EUR: pl.Float64,
            ProductColumns.UNIT_MEASURE: pl.String,
            ProductColumns.APPROX_WEIGHT_KG: pl.Float64,
            ProductColumns.PRICE_PER_KG: pl.Float64,
            ProductColumns.SOURCE_QUERY: pl.String,
            ProductColumns.URL: pl.String,
        }
