"""Normalize shopping-list lines: text cleanup, search query, requested amount."""

from __future__ import annotations

import unicodedata
from typing import (
    FrozenSet, 
    Optional,
    Dict,
    Any,
)

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.units import (
    is_count_unit, 
    _to_float, 
    to_kg,
)
from supermarket_linkage.regex_consts import NON_WORD, QUANTITY

# Spanish grocery stopwords (hard-coded); the ones referring to quantity are stripped via
# QUANTITY separately. 
STOPWORDS: FrozenSet[str] = frozenset(
    {
        "a",
        "al",
        "aprox",
        "aproximada",
        "aproximado",
        "con",
        "de",
        "del",
        "el",
        "en",
        "la",
        "las",
        "los",
        "o",
        "pack",
        "packs",
        "para",
        "por",
        "un",
        "una",
        "unas",
        "unos",
        "y",
    }
)


def strip_accents(text: str) -> str:
    """
    We remove diacritics and accents in general via NFKD decomposition.
    """
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    """
    This is a mini, basic, normalized for text, where we lowercase, strip accents,
    strip punctuation and drop very basic stopwords from the grocery domain. We return
    space-joined content tokens unless nothing remains; in this case, we return an empty string.
    """
    lowered = strip_accents(text).lower()
    cleaned = NON_WORD.sub(" ", lowered)
    tokens = [t for t in cleaned.split() if t and t not in STOPWORDS]
    return " ".join(tokens)


def parse_requested_amount_kg(text: str) -> Optional[float]:
    """
    This function parses first mass/volume quantity and transforms it to kilograms
    (either kilograms or liters, as it is the same for both of them in terms of price/kg)
    count units (unidad or ud) are ignore here, so amount stays None.
    """
    match = QUANTITY.search(text)
    if match is None:
        return None
    value = _to_float(raw=match.group("value"))
    if value is None:
        return None
    unit = match.group("unit")
    if is_count_unit(unit):
        return None
    return to_kg(value, unit)


def extract_search_query(text: str) -> str:
    """
    This function provides normalized product tokens
    where we have removed quantity phrases via a catalog search.
    """
    without_qty = QUANTITY.sub(" ", text)
    return normalize_text(without_qty)


def _row_fields(query: str) -> Dict[str, Any]:
    """
    This function extracts normalized product tokens out of a query and returns
    query_norm, search_query and requested_amount_kg for each product.
    """
    search = extract_search_query(text=query)
    # we use the same token set for query and search
    return {
        "query_norm": search,
        "search_query": search,
        "requested_amount_kg": parse_requested_amount_kg(text=query),
    }


class TextNormalizer(BasePreprocessor):
    """
    We derive search and query normalization columns as well as requested kilograms
    from a query column.
    """

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        We add the columns query_norm, search_query, and requested_amount_kg out of
        a original df (polars DataFrame) that contains a string column named query, so the output contains
        the original column plus the three extra columns. 
        """
        if "query" not in df.columns:
            raise ValueError("TextNormalizer requires a 'query' column.")
        queries = df.get_column("query").to_list()
        query_norm = [query if query is not None else "" for query in queries]
        derived_information = [_row_fields(query=query) for query in query_norm]
        extra_columns = pl.DataFrame(derived_information).select(
            ["query_norm", "search_query", "requested_amount_kg"]
        )
        # Drop prior derived cols so with_columns does not duplicate names.
        base = df.drop(
            [c for c in ("query_norm", "search_query", "requested_amount_kg") if c in df.columns]
        )
        return base.with_columns(extra_columns)
