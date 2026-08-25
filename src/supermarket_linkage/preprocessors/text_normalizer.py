"""Normalize shopping-list lines: text cleanup, search query, requested amount."""

from __future__ import annotations

import re
import unicodedata
from typing import (
    Any,
    Dict,
    FrozenSet,
    List,
    Optional,
)

import polars as pl

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor
from supermarket_linkage.preprocessors.consts import _to_float, is_count_unit, to_kg
from supermarket_linkage.regex_consts import NON_WORD, QUANTITY

# Spanish grocery stopwords (hard-coded); the ones referring to quantity are stripped via
# QUANTITY separately. ``o`` is kept here for leftover fragments; OR-splitting runs first.
STOPWORDS: FrozenSet[str] = frozenset(
    {
        "a",
        "al",
        "aprox",
        "aproximada",
        "aproximado",
        "ciento",
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

# Common paste typos / Spanish vs Italian pasta spelling → catalog form.
TOKEN_ALIASES: Dict[str, str] = {
    "espagueti": "spaghetti",
    "espaguetis": "spaghetti",
    "espaguetti": "spaghetti",
    "espaguettis": "spaghetti",
    # Mercadona Algolia titles use batata, not boniato.
    "boniato": "batata",
    "boniatos": "batata",
    # rough_stem("nueces") → "nuec"; catalog uses singular "nuez".
    "nueces": "nuez",
}

# When the shopper writes generic «pasta», also search common shape names.
_PASTA_SHAPE_ALTERNATIVES: tuple[str, ...] = (
    "spaghetti",
    "macarron",
    "macarrones",
    "espirales",
    "tallarines",
    "fideos",
)

# Split shopping-list OR before stopword drop: «leche o bebida vegetal».
_OR_SPLIT: re.Pattern[str] = re.compile(r"\s+o\s+", re.IGNORECASE)

# Leading catalog stems that are form/cut, not the product head (copos de avena…).
# Values are rough_stem forms so they match after plural stemming.
NAME_FORMAT_PREFIXES: FrozenSet[str] = frozenset(
    {
        "bebida",
        "caldo",
        "copo",
        "crema",
        "dado",
        "filete",
        "loncha",
        "pechuga",
        "salsa",
        "trozo",
        "zumo",
    }
)


def strip_accents(text: str) -> str:
    """
    We remove diacritics and accents in general via NFKD decomposition.
    """
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def rough_stem(token: str) -> str:
    """
    Light Spanish plural stem for grocery tokens (lentejas→lenteja, filetes→filete).
    """
    if len(token) <= 3:
        return token
    if token.endswith("tes") and len(token) > 4:
        return token[:-1]
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


def normalize_text(text: str) -> str:
    """
    This is a mini, basic, normalized for text, where we lowercase, strip accents,
    strip punctuation and drop very basic stopwords from the grocery domain. We return
    space-joined content tokens unless nothing remains; in this case, we return an empty string.
    """
    lowered = strip_accents(text).lower()
    cleaned = NON_WORD.sub(" ", lowered)
    tokens = [
        TOKEN_ALIASES.get(t, t)
        for t in cleaned.split()
        if t and t not in STOPWORDS
    ]
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


def _expand_pasta_alternatives(query_norm: str) -> List[str]:
    """If ``pasta`` is a token, also emit shape-specific queries for Mercadona titles."""
    tokens = query_norm.split()
    if "pasta" not in tokens:
        return [query_norm]
    out: List[str] = [query_norm]
    for shape in _PASTA_SHAPE_ALTERNATIVES:
        replaced = " ".join(shape if t == "pasta" else t for t in tokens)
        if replaced and replaced not in out:
            out.append(replaced)
    return out


def extract_search_alternatives(text: str) -> List[str]:
    """
    Normalized search strings for one list line (OR branches + pasta expansions).

    Pre: raw shopping-list line (may include quantities and ``o`` alternatives).
    Post: de-duplicated non-empty norms; empty list only when nothing remains.
    """
    without_qty = QUANTITY.sub(" ", text)
    branches = _OR_SPLIT.split(without_qty)
    alts: List[str] = []
    for branch in branches:
        norm = normalize_text(branch)
        if not norm:
            continue
        for expanded in _expand_pasta_alternatives(norm):
            if expanded and expanded not in alts:
                alts.append(expanded)
    return alts


def extract_search_query(text: str) -> str:
    """
    Primary normalized product tokens for catalog search (first OR / pasta alternative).
    """
    alts = extract_search_alternatives(text)
    return alts[0] if alts else ""


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
