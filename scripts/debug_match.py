#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl
import polars_distance as pld
from supermarket_linkage.consts import (
    JW_MAX_DISTANCE,
    MERCADONA_ALGOLIA_API_KEY,
    MERCADONA_ALGOLIA_APP_ID,
    MERCADONA_ALGOLIA_HOST,
    MERCADONA_ALGOLIA_QUERIES_PATH,
)
from supermarket_linkage.pipeline.heuristic_stage import heuristic_pass
from supermarket_linkage.preprocessors.text_normalizer import (
    extract_search_alternatives,
    normalize_text,
)

INDEX = "products_prod_mad1_es"
URL = f"{MERCADONA_ALGOLIA_HOST}{MERCADONA_ALGOLIA_QUERIES_PATH}"


def _search(query: str, n: int) -> list[dict]:
    body = {
        "requests": [
            {
                "indexName": INDEX,
                "params": urlencode({"query": query, "hitsPerPage": n}),
            }
        ]
    }
    req = Request(
        URL
        + "?"
        + urlencode(
            {
                "x-algolia-application-id": MERCADONA_ALGOLIA_APP_ID,
                "x-algolia-api-key": MERCADONA_ALGOLIA_API_KEY,
            }
        ),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    return data["results"][0].get("hits", [])


def _jw(a: str, b: str) -> float | None:
    df = pl.DataFrame({"a": [a], "b": [b]}).with_columns(
        pld.col("a").dist_str.jaro_winkler(pl.col("b")).alias("d")
    )
    return float(df["d"][0])


def _dump_line(raw: str, hits_per: int) -> None:
    alts = extract_search_alternatives(raw)
    print(f"=== {raw!r}")
    print(f"alternativas: {alts or ['(vacío)']}")
    for alt in alts or [""]:
        hits = _search(alt or raw, hits_per) if (alt or raw.strip()) else []
        print(f"-- búsqueda {alt!r} ({len(hits)} resultados)")
        if not hits:
            print("   (sin resultados)")
            continue
        any_pass = False
        for h in hits:
            name = h.get("display_name") or h.get("name") or ""
            nn = normalize_text(name)
            ok = heuristic_pass(alt, nn)
            any_pass = any_pass or ok
            dist = _jw(alt, nn)
            mark = "ok" if ok else "no"
            extra = ""
            if dist is not None:
                keep = dist < JW_MAX_DISTANCE or ok
                extra = f" JW={dist:.3f}{' se queda' if keep else ' fuera'}"
            print(f"   [{mark}] {name} | {nn}{extra}")
        if not any_pass:
            print("   → ninguna pasa heurística")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("lines", nargs="*")
    p.add_argument("-f", "--file", type=Path)
    p.add_argument("-n", type=int, default=6)
    p.add_argument("--warehouse", default="mad1")
    args = p.parse_args()
    global INDEX
    INDEX = f"products_prod_{args.warehouse}_es"
    lines: list[str] = list(args.lines)
    if args.file:
        lines.extend(
            ln.strip()
            for ln in args.file.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        )
    if not lines:
        lines = [ln.strip() for ln in sys.stdin if ln.strip()]
    if not lines:
        p.error("pasa líneas, -f archivo, o stdin")
    for line in lines:
        _dump_line(line, args.n)


if __name__ == "__main__":
    main()
