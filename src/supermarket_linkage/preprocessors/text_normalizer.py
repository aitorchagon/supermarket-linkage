"""Normalize shopping-list lines: text cleanup, search query, requested amount."""

from __future__ import annotations

import unicodedata

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.units import is_count_unit, parse_numeric, to_kg
from supermarket_linkage.regex_consts import NON_WORD, QUANTITY

# Spanish grocery noise; quantity tokens are stripped via QUANTITY separately.
STOPWORDS: frozenSet[str] = frozenset(
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
    """Remove diacritics via NFKD decomposition."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    """Lowercase, strip accents/punctuation, drop stopwords.

    Pre: ``text`` is a non-null string (may be empty).
    Post: Space-joined content tokens; empty string if nothing remains.
    """
    lowered = strip_accents(text).lower()
    cleaned = NON_WORD.sub(" ", lowered)
    tokens = [t for t in cleaned.split() if t and t not in STOPWORDS]
    return " ".join(tokens)


def parse_requested_amount_kg(text: str) -> float | None:
    """Parse first mass/volume quantity in ``text`` as kg-equivalent.

    Count units (ud/unidad) are ignored here — amount stays None.
    """
    match = QUANTITY.search(text)
    if match is None:
        return None
    value = parse_numeric(match.group("value"))
    if value is None:
        return None
    unit = match.group("unit")
    if is_count_unit(unit):
        return None
    return to_kg(value, unit)


def extract_search_query(text: str) -> str:
    """Normalized product tokens with quantity phrases removed (catalog search)."""
    without_qty = QUANTITY.sub(" ", text)
    return normalize_text(without_qty)


def _row_fields(query: str) -> dict[str, object]:
    search = extract_search_query(query)
    # query_norm: same token set used for matching / dedupe as search.
    return {
        "query_norm": search,
        "search_query": search,
        "requested_amount_kg": parse_requested_amount_kg(query),
    }


class TextNormalizer(BasePreprocessor):
    """Derive search/query norms and requested kg from a ``query`` column."""

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add ``query_norm``, ``search_query``, ``requested_amount_kg``.

        Pre: ``df`` has a string column ``query``.
        Post: Same rows plus the three derived columns.
        """
        if "query" not in df.columns:
            raise ValueError("TextNormalizer requires a 'query' column.")

        derived = [
            _row_fields(q if q is not None else "")
            for q in df.get_column("query").to_list()
        ]
        extra = pl.DataFrame(
            {
                "query_norm": [d["query_norm"] for d in derived],
                "search_query": [d["search_query"] for d in derived],
                "requested_amount_kg": [d["requested_amount_kg"] for d in derived],
            }
        )
        # Drop prior derived cols so with_columns does not duplicate names.
        base = df.drop(
            [c for c in ("query_norm", "search_query", "requested_amount_kg") if c in df.columns]
        )
        return base.with_columns(extra)
