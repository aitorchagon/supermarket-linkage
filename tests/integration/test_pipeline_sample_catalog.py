from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from supermarket_linkage.pipeline.linkage_orchestrator import LinkageOrchestrator
from supermarket_linkage.preprocessors.price_normalizer import PriceNormalizer
from supermarket_linkage.preprocessors.text_normalizer import (
    extract_search_alternatives,
    extract_search_query,
    normalize_text,
)
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.schemas.product_table import ProductColumns, ProductTable
from supermarket_linkage.worker.warmup import TokenOverlapEmbedder

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_catalog.json"


def _load_catalog() -> pl.DataFrame:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    df = pl.DataFrame(raw)
    df = ProductTable.enforce_schema(df)
    return PriceNormalizer().process(df)


def _search_offline(catalog: pl.DataFrame, query_norm: str) -> pl.DataFrame:
    """Return products whose name tokens contain all query tokens; tag source_query."""
    q_tokens = query_norm.split()
    if not q_tokens:
        return ProductTable.as_empty_dataframe()

    rows = []
    for row in catalog.iter_rows(named=True):
        name_norm = normalize_text(row[ProductColumns.NAME] or "")
        name_tokens = set(name_norm.split())
        if all(t in name_tokens for t in q_tokens):
            rows.append(row)

    if not rows:
        return ProductTable.as_empty_dataframe()

    hits = pl.DataFrame(rows)
    hits = hits.with_columns(pl.lit(query_norm).alias(ProductColumns.SOURCE_QUERY))
    return ProductTable.enforce_schema(hits)


@pytest.fixture(scope="module")
def catalog() -> pl.DataFrame:
    return _load_catalog()


@pytest.fixture
def orchestrator() -> LinkageOrchestrator:
    return LinkageOrchestrator(embedder=TokenOverlapEmbedder(), store="mercadona")


def test_sample_catalog_size(catalog: pl.DataFrame) -> None:
    assert 30 <= catalog.height <= 50


def test_pipeline_arroz_basmati_picks_cheaper_per_kg(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "arroz basmati 1500 g"
    q_norm = extract_search_query(query)
    products = _search_offline(catalog, q_norm)
    assert products.height >= 2

    result = orchestrator.link_line(query, products, line_index=0)
    assert result[LineResultColumns.STATUS][0] == "matched"
    # 500 g pack is 1.90 €/kg vs 1 kg at 1.50 €/kg → 1 kg wins Branch A.
    assert result[LineResultColumns.PRODUCT_ID][0] == "4245"
    assert result[LineResultColumns.UNITS_NEEDED][0] == 2
    assert result[LineResultColumns.PACK_SIZE_MISSING][0] is False


def test_pipeline_leche_entera(catalog: pl.DataFrame, orchestrator: LinkageOrchestrator) -> None:
    query = "leche entera 1l"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=1)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "30902"
    assert result[LineResultColumns.UNITS_NEEDED][0] == 1


def test_pipeline_branch_b_unidad_no_weight(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "huevos camperos"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=2)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "8001"
    assert result[LineResultColumns.PRICE_PER_KG][0] is None
    assert result[LineResultColumns.UNITS_NEEDED][0] == 1


def test_pipeline_no_match(catalog: pl.DataFrame, orchestrator: LinkageOrchestrator) -> None:
    query = "salsa de soja premium inexistente"
    products = _search_offline(catalog, extract_search_query(query))
    result = orchestrator.link_line(query, products, line_index=3)
    assert result[LineResultColumns.STATUS][0] == "no_match"
    assert result[LineResultColumns.PRODUCT_ID][0] is None


def test_pipeline_or_alternative_picks_leche(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "leche o bebida vegetal 6l"
    alts = extract_search_alternatives(query)
    assert alts[0] == "leche"
    products = _search_offline(catalog, alts[0])
    result = orchestrator.link_line(query, products, line_index=4, query_norm=alts[0])
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] in {"30902", "30903", "30910"}


def test_pipeline_queso_fresco_batido_drops_paquetes(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    query = "Queso fresco batido 2 paquetes"
    q_norm = extract_search_query(query)
    assert q_norm == "queso fresco batido"
    products = _search_offline(catalog, q_norm)
    result = orchestrator.link_line(query, products, line_index=5, query_norm=q_norm)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "55001"


def test_pipeline_link_lines_batch(
    catalog: pl.DataFrame, orchestrator: LinkageOrchestrator
) -> None:
    lines = pl.DataFrame(
        {
            "query": ["arroz basmati 1 kg", "aceite de oliva virgen extra 1l", "xyzzy no product"],
        }
    )
    by_q: dict[str, pl.DataFrame] = {}
    for q in lines["query"].to_list():
        qn = extract_search_query(q)
        by_q[qn] = _search_offline(catalog, qn)

    out = orchestrator.link_lines(lines, by_q)
    assert out.height == 3
    assert out[LineResultColumns.STATUS].to_list()[0] == "matched"
    assert out[LineResultColumns.STATUS].to_list()[1] == "matched"
    assert out[LineResultColumns.STATUS].to_list()[2] == "no_match"


def test_pipeline_rescues_non_heuristic_candidate_via_semantic_and_distance(
    orchestrator: LinkageOrchestrator,
) -> None:
    query = "aceite de oliva virgen extraa 1l"
    q_norm = "aceite oliva virgen extraa"
    products = ProductTable.enforce_schema(
        pl.DataFrame(
            {
                ProductColumns.PRODUCT_ID: ["69066", "30902"],
                ProductColumns.NAME: ["Aceite de oliva virgen extra", "Leche entera 1 l"],
                ProductColumns.PRICE_EUR: [4.50, 0.84],
                ProductColumns.UNIT_MEASURE: ["LITRO", "LITRO"],
                ProductColumns.APPROX_WEIGHT_KG: [1.0, 1.0],
                ProductColumns.PRICE_PER_KG: [4.50, 0.84],
                ProductColumns.SOURCE_QUERY: [q_norm, q_norm],
            }
        )
    )
    result = orchestrator.link_line(query, products, line_index=0, query_norm=q_norm)
    assert result[LineResultColumns.STATUS][0] == "matched"
    assert result[LineResultColumns.PRODUCT_ID][0] == "69066"
    assert result[LineResultColumns.SEMANTIC_SCORE][0] >= 0.75
    assert result[LineResultColumns.JW_SIMILARITY][0] > 0.9
