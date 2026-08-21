from typing import Any, Dict, Type

import polars as pl

from supermarket_linkage.schemas.base import ColumnsEnumBase, TableSchemaBase


class LineResultColumns(ColumnsEnumBase):
    LINE_INDEX = "line_index"
    QUERY = "query"
    QUERY_NORM = "query_norm"
    STATUS = "status"
    STORE = "store"
    PRODUCT_ID = "product_id"
    NAME = "name"
    BRAND = "brand"
    PRICE_EUR = "price_eur"
    PROMO_PRICE_EUR = "promo_price_eur"
    EFFECTIVE_PRICE_EUR = "effective_price_eur"
    PRICE_PER_KG = "price_per_kg"
    UNIT_MEASURE = "unit_measure"
    JW_SIMILARITY = "jw_similarity"
    SEMANTIC_SCORE = "semantic_score"
    MATCH_STAGE = "match_stage"
    REQUESTED_AMOUNT_KG = "requested_amount_kg"
    PACK_SIZE_KG = "pack_size_kg"
    UNITS_NEEDED = "units_needed"
    LINE_TOTAL_PRICE_EUR = "line_total_price_eur"
    PACK_SIZE_MISSING = "pack_size_missing"
    PRODUCT_URL = "product_url"


class LineResultTable(TableSchemaBase):
    @classmethod
    def get_columns_enum(cls) -> Type[ColumnsEnumBase]:
        return LineResultColumns

    @classmethod
    def dtypes(cls) -> Dict[str, Any]:
        return {
            LineResultColumns.LINE_INDEX: pl.Int64,
            LineResultColumns.QUERY: pl.String,
            LineResultColumns.QUERY_NORM: pl.String,
            LineResultColumns.STATUS: pl.String,
            LineResultColumns.STORE: pl.String,
            LineResultColumns.PRODUCT_ID: pl.String,
            LineResultColumns.NAME: pl.String,
            LineResultColumns.BRAND: pl.String,
            LineResultColumns.PRICE_EUR: pl.Float64,
            LineResultColumns.PROMO_PRICE_EUR: pl.Float64,
            LineResultColumns.EFFECTIVE_PRICE_EUR: pl.Float64,
            LineResultColumns.PRICE_PER_KG: pl.Float64,
            LineResultColumns.UNIT_MEASURE: pl.String,
            LineResultColumns.JW_SIMILARITY: pl.Float64,
            LineResultColumns.SEMANTIC_SCORE: pl.Float64,
            LineResultColumns.MATCH_STAGE: pl.String,
            LineResultColumns.REQUESTED_AMOUNT_KG: pl.Float64,
            LineResultColumns.PACK_SIZE_KG: pl.Float64,
            LineResultColumns.UNITS_NEEDED: pl.Int64,
            LineResultColumns.LINE_TOTAL_PRICE_EUR: pl.Float64,
            LineResultColumns.PACK_SIZE_MISSING: pl.Boolean,
            LineResultColumns.PRODUCT_URL: pl.String,
        }
