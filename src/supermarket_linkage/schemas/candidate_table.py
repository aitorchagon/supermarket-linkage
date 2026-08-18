"""Candidate products with stage flags and similarity scores."""

from typing import Any, Dict, Type

import polars as pl

from supermarket_linkage.schemas.base import ColumnsEnumBase, TableSchemaBase


class CandidateColumns(ColumnsEnumBase):
    PRODUCT_ID = "product_id"
    NAME = "name"
    NAME_NORM = "name_norm"
    BRAND = "brand"
    PRICE_EUR = "price_eur"
    PROMO_PRICE_EUR = "promo_price_eur"
    UNIT_PRICE_EUR = "unit_price_eur"
    UNIT_MEASURE = "unit_measure"
    APPROX_WEIGHT_KG = "approx_weight_kg"
    PRICE_PER_KG = "price_per_kg"
    SOURCE_QUERY = "source_query"
    QUERY = "query"
    QUERY_NORM = "query_norm"
    URL = "url"
    HEURISTIC_PASS = "heuristic_pass"
    SEMANTIC_SCORE = "semantic_score"
    JW_SIMILARITY = "jw_similarity"
    JW_DISTANCE = "jw_distance"


class CandidateTable(TableSchemaBase):
    @classmethod
    def get_columns_enum(cls) -> Type[ColumnsEnumBase]:
        return CandidateColumns

    @classmethod
    def dtypes(cls) -> Dict[str, Any]:
        return {
            CandidateColumns.PRODUCT_ID: pl.String,
            CandidateColumns.NAME: pl.String,
            CandidateColumns.NAME_NORM: pl.String,
            CandidateColumns.BRAND: pl.String,
            CandidateColumns.PRICE_EUR: pl.Float64,
            CandidateColumns.PROMO_PRICE_EUR: pl.Float64,
            CandidateColumns.UNIT_PRICE_EUR: pl.Float64,
            CandidateColumns.UNIT_MEASURE: pl.String,
            CandidateColumns.APPROX_WEIGHT_KG: pl.Float64,
            CandidateColumns.PRICE_PER_KG: pl.Float64,
            CandidateColumns.SOURCE_QUERY: pl.String,
            CandidateColumns.QUERY: pl.String,
            CandidateColumns.QUERY_NORM: pl.String,
            CandidateColumns.URL: pl.String,
            CandidateColumns.HEURISTIC_PASS: pl.Boolean,
            CandidateColumns.SEMANTIC_SCORE: pl.Float64,
            CandidateColumns.JW_SIMILARITY: pl.Float64,
            CandidateColumns.JW_DISTANCE: pl.Float64,
        }
