from __future__ import annotations

from typing import (
    Sequence, 
    Optional,
    List,
)

import polars as pl

from supermarket_linkage.pipeline.base_stage import BaseStage
from supermarket_linkage.pipeline.blocking_stage import BlockingStage
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
from supermarket_linkage.pipeline.consts import (
    STATUS_MATCHED,
    STATUS_NO_MATCH,
    MATCH_STAGE_DISTANCE
)


def select_winner(survivors: pl.DataFrame) -> pl.DataFrame:
    """
    This function allows to select the winner. We have two different branches:
    - lowest price per kilogram, then highest Jaro-Winkler distance
    - Highest Jaro-Winkler distance, in case we do not have price per kilogram.
    
    We have the survivors from stage 4 and we return the winner.
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
    This function allows to build CandidateTable rows from ProductTable search hits, that is, we are converting,
    following our own schemas, product rows to candidate rows.
    """
    query_norm = query_norm if query_norm is not None else extract_search_query(query)
    product_height = products.height
    if product_height == 0:
        empty = CandidateTable.as_empty_dataframe()
        return empty

    names = products[ProductColumns.NAME].to_list() if ProductColumns.NAME in products.columns else [None] * product_height
    name_norms = [normalize_text(normalized_name or "") for normalized_name in names]

    # Carry product columns; fill query fields.
    base = products
    extras = {
        CandidateColumns.NAME_NORM: name_norms,
        CandidateColumns.QUERY: [query] * product_height,
        CandidateColumns.QUERY_NORM: [query_norm] * product_height,
        CandidateColumns.HEURISTIC_PASS: [False] * product_height,
        CandidateColumns.SEMANTIC_SCORE: [None] * product_height,
        CandidateColumns.JW_SIMILARITY: [None] * product_height,
        CandidateColumns.JW_DISTANCE: [None] * product_height,
    }
    # Drop if already present to avoid duplicate columns.
    drop = [column for column  in extras if column in base.columns]
    if drop:
        base = base.drop(drop)
    out = base.with_columns(
        [pl.Series(column, values) for column, values in extras.items()]
    )
    return CandidateTable.enforce_schema(out)


class LinkageOrchestrator:
    """
    This orchestrator manages a linkage pipeline. This pipeline has the following stages:
    - Heuristic stage.
    - Blocking stage.
    - Semantic stage.
    - Distance stage.
    - Determine the winner.
    - Resolve quantities.
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
        """
        This function applies the stage chain and returns the final survivors, which may or may not be 
        empty
        """
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
        This function allows to link a one shopping-list line to a catalog hit.
        Products are search hits for this line with the ProductTable schema and the output is a LineResultTable,
        with a single row, with quantity fields, that contains whether we have a match or not.
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
        # Prefer explicit effective from product frame if present on winner.
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
        This function allows to link many shopping-lists lines to many catalog hits.
        Products are search hits for this line with the ProductTable schema and the output is a LineResultTable,
        with a single row, with quantity fields, that contains whether we have a match or not.
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
