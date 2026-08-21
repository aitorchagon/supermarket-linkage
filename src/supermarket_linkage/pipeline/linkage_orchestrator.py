from __future__ import annotations

from typing import (
    List,
    Optional,
    Sequence,
)

import polars as pl

from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.pipeline.blocking_stage import BlockingStage
from supermarket_linkage.pipeline.consts import MATCH_STAGE_DISTANCE, STATUS_MATCHED, STATUS_NO_MATCH
from supermarket_linkage.pipeline.distance_stage import DistanceStage
from supermarket_linkage.pipeline.heuristic_stage import HeuristicStage
from supermarket_linkage.pipeline.semantic_stage import Embedder, SemanticStage
from supermarket_linkage.preprocessors.quantity_resolver import QuantityResolver
from supermarket_linkage.preprocessors.text_normalizer import (
    extract_search_query,
    normalize_text,
    parse_requested_amount_kg,
)
from supermarket_linkage.schemas.candidate_table import CandidateColumns, CandidateTable
from supermarket_linkage.schemas.line_result_table import LineResultColumns, LineResultTable
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable


def select_winner(survivors: pl.DataFrame) -> pl.DataFrame:
    """
    Pick one winner among stage-4 survivors.

    Branch A (any priced ``price_per_kg``): lowest price/kg, then highest JW similarity.
    Branch B (all null): highest JW similarity.
    """
    if survivors.height == 0:
        return survivors

    priced = survivors.filter(pl.col(CandidateColumns.PRICE_PER_KG).is_not_null())
    if priced.height > 0:
        return priced.sort(
            [CandidateColumns.PRICE_PER_KG, CandidateColumns.JW_SIMILARITY],
            descending=[False, True],
        ).head(1)
    return survivors.sort(CandidateColumns.JW_SIMILARITY, descending=True).head(1)


def products_to_candidates(
    products: pl.DataFrame,
    *,
    query: str,
    query_norm: Optional[str] = None,
) -> pl.DataFrame:
    """
    Build CandidateTable rows from ProductTable search hits.
    """
    query_norm = query_norm if query_norm is not None else extract_search_query(query)
    product_height = products.height
    if product_height == 0:
        return CandidateTable.as_empty_dataframe()

    drop = [
        col
        for col in (
            CandidateColumns.NAME_NORM,
            CandidateColumns.QUERY,
            CandidateColumns.QUERY_NORM,
            CandidateColumns.HEURISTIC_PASS,
            CandidateColumns.SEMANTIC_SCORE,
            CandidateColumns.JW_SIMILARITY,
            CandidateColumns.JW_DISTANCE,
        )
        if col in products.columns
    ]
    base = products.drop(drop) if drop else products
    out = base.with_columns(
        [
            pl.col(ProductColumns.NAME)
            .fill_null("")
            .map_elements(normalize_text, return_dtype=pl.String)
            .alias(CandidateColumns.NAME_NORM),
            pl.lit(query).alias(CandidateColumns.QUERY),
            pl.lit(query_norm).alias(CandidateColumns.QUERY_NORM),
            pl.lit(False).alias(CandidateColumns.HEURISTIC_PASS),
            pl.lit(None, dtype=pl.Float64).alias(CandidateColumns.SEMANTIC_SCORE),
            pl.lit(None, dtype=pl.Float64).alias(CandidateColumns.JW_SIMILARITY),
            pl.lit(None, dtype=pl.Float64).alias(CandidateColumns.JW_DISTANCE),
        ]
    )
    return CandidateTable.enforce_schema(out)


class LinkageOrchestrator:
    """
    Linkage pipeline: heuristic → blocking → semantic → distance → winner → quantity.
    """

    def __init__(
        self,
        embedder: Embedder,
        stages: Optional[Sequence[BaseStage]] = None,
        store: str = "mercadona",
        quantity_resolver: Optional[QuantityResolver] = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.quantity_resolver = quantity_resolver or QuantityResolver()
        if stages is not None:
            self.stages: List[BaseStage] = list(stages)
        else:
            self.stages = [
                HeuristicStage(),
                BlockingStage(),
                SemanticStage(embedder=embedder),
                DistanceStage(),
            ]

    def run_stages(self, candidates: pl.DataFrame) -> pl.DataFrame:
        """Apply the stage chain; may return an empty CandidateTable."""
        current = CandidateTable.enforce_schema(candidates)
        for stage in self.stages:
            current = stage.process(current)
            if current.height == 0:
                return CandidateTable.enforce_schema(current)
        return current

    def link_line(
        self,
        query: str,
        products: pl.DataFrame,
        *,
        line_index: int = 0,
        query_norm: Optional[str] = None,
        requested_amount_kg: Optional[float] = None,
        effective_price_col: str = ProductColumns.PRICE_EUR,
    ) -> pl.DataFrame:
        """
        Link one shopping-list line to catalog hits.

        Pre: ``products`` is ProductTable-shaped for this line.
        Post: one-row LineResultTable (``matched`` or ``no_match``) with quantity fields.
        """
        query_norm = query_norm if query_norm is not None else extract_search_query(query)
        if requested_amount_kg is None:
            requested_amount_kg = parse_requested_amount_kg(query)

        candidates = products_to_candidates(products, query=query, query_norm=query_norm)
        survivors = self.run_stages(candidates)
        winner = select_winner(survivors)

        if winner.height == 0:
            result = pl.DataFrame(
                {
                    LineResultColumns.LINE_INDEX: [line_index],
                    LineResultColumns.QUERY: [query],
                    LineResultColumns.QUERY_NORM: [query_norm],
                    LineResultColumns.STATUS: [STATUS_NO_MATCH],
                    LineResultColumns.STORE: [self.store],
                    LineResultColumns.REQUESTED_AMOUNT_KG: [requested_amount_kg],
                }
            )
            return self.quantity_resolver.process(result)

        row = winner.row(0, named=True)
        price = row.get(CandidateColumns.PRICE_EUR)
        promo = row.get(CandidateColumns.PROMO_PRICE_EUR)
        effective = row.get(effective_price_col, price)
        if effective is None:
            effective = price

        result = pl.DataFrame(
            {
                LineResultColumns.LINE_INDEX: [line_index],
                LineResultColumns.QUERY: [query],
                LineResultColumns.QUERY_NORM: [query_norm],
                LineResultColumns.STATUS: [STATUS_MATCHED],
                LineResultColumns.STORE: [self.store],
                LineResultColumns.PRODUCT_ID: [row.get(CandidateColumns.PRODUCT_ID)],
                LineResultColumns.NAME: [row.get(CandidateColumns.NAME)],
                LineResultColumns.BRAND: [row.get(CandidateColumns.BRAND)],
                LineResultColumns.PRICE_EUR: [price],
                LineResultColumns.PROMO_PRICE_EUR: [promo],
                LineResultColumns.EFFECTIVE_PRICE_EUR: [effective],
                LineResultColumns.PRICE_PER_KG: [row.get(CandidateColumns.PRICE_PER_KG)],
                LineResultColumns.UNIT_MEASURE: [row.get(CandidateColumns.UNIT_MEASURE)],
                LineResultColumns.JW_SIMILARITY: [row.get(CandidateColumns.JW_SIMILARITY)],
                LineResultColumns.SEMANTIC_SCORE: [row.get(CandidateColumns.SEMANTIC_SCORE)],
                LineResultColumns.MATCH_STAGE: [MATCH_STAGE_DISTANCE],
                LineResultColumns.REQUESTED_AMOUNT_KG: [requested_amount_kg],
                LineResultColumns.PRODUCT_URL: [row.get(CandidateColumns.URL)],
                "approx_weight_kg": [row.get(CandidateColumns.APPROX_WEIGHT_KG)],
            }
        )
        return self.quantity_resolver.process(result)

    def link_lines(
        self,
        lines: pl.DataFrame,
        products_by_query_norm: dict[str, pl.DataFrame],
    ) -> pl.DataFrame:
        """
        Link many shopping-list lines.

        Pre: ``lines`` has a ``query`` column; map is ProductTable frames by query_norm.
        Post: LineResultTable with one row per input line.
        """
        if "query" not in lines.columns:
            raise ValueError("link_lines requires a 'query' column.")

        results: List[pl.DataFrame] = []
        for i, row in enumerate(lines.iter_rows(named=True)):
            query = row["query"] or ""
            query_norm = row.get("query_norm")
            if not query_norm:
                query_norm = extract_search_query(text=query)
            requested = row.get("requested_amount_kg")
            products = products_by_query_norm.get(query_norm)
            if products is None:
                products = ProductTable.as_empty_dataframe()
            results.append(
                self.link_line(
                    query,
                    products,
                    line_index=int(row.get("line_index", i)),
                    query_norm=query_norm,
                    requested_amount_kg=requested,
                )
            )
        if not results:
            return LineResultTable.as_empty_dataframe()
        return pl.concat(results, how="diagonal_relaxed")
