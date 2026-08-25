# DESIGN — record-linkage-supermarket-online

Shopping-list → catalog record linkage. User picks **one** store, pastes a list, gets best SKU per line (price/kg when possible), `units_needed`, and exportable product links.

**v1 store:** Mercadona only (DIA / Carrefour stubbed).  
**Package:** `supermarket_linkage` (folder may still be named `record-linkage-dia-online`).  
**Docstrings:** short and direct.

---

## 1. Store selector (not aggregation)

**Why:** User shops at one chain per run. Selector matches that intent and keeps the pipeline store-agnostic.

**Why not** multi-store price comparison in v1: different clients (Playwright for DIA/Carrefour), promo fields, and export URL patterns — out of scope.

**Decision:** UI `selectbox` with Mercadona enabled; DIA/Carrefour shown as "Próximamente". `CatalogClientFactory.get(store)` returns the client; stubs raise `NotImplementedError`.

---

## 2. Quantity fulfillment

After the winner is chosen, parse requested amount vs pack size:

`units_needed = ceil(requested / pack_size)` (min 1).  
`line_total_price = units_needed × effective_unit_price`.

**Why after winner:** ranking stays fair on single-unit `price_per_kg`. Quantity is a shopping summary concern.

Missing pack size → `units_needed = 1`, `pack_size_missing = True`.

---

## 3. Export / GDPR

**v1:** public product URLs, CSV, clipboard text with quantities. No Mercadona login, no cart write, no long-term list storage (jobs ephemeral + TTL).

**Why:** Mercadona has no public pre-fill cart URL. Links still save search time.

**GDPR (v1):** list text goes to the worker for processing and is not retained after job TTL. No account credentials → no special consent flow beyond a normal privacy notice.

**v2 (documented only):** authenticated cart push needs explicit opt-in, token hygiene, purpose limitation, never auto-checkout.

---

## 4. Master–worker

| Role | Host | Does |
|------|------|------|
| Master | Streamlit Community Cloud | UI, submit, poll, export |
| Worker | HF Spaces (Docker, CPU Basic) | catalog fetch, embeddings, pipeline, job API |

Master never loads the embedding model or hits Mercadona directly.

---

## 5. Redis — deferred

**Why not in v1:** one container, one process. `InMemoryJobStore` is enough. Redis does not speed a single worker; it coordinates replicas / shared state.

**When:** 2+ replicas behind a load balancer, persistent job history, or global rate limits across instances.

**Migration:** `JobStore` ABC → `InMemoryJobStore` (v1) → `RedisJobStore` later. HTTP contract unchanged. Restart loses in-flight jobs — acceptable at this scale.

---

## 6. Matching rules (no weighted score)

| Stage | Rule |
|-------|------|
| Heuristic | Exact normalized name **or** all query tokens ⊆ product name |
| Blocking | Same `source_query` block |
| Semantic | Cosine ≥ `SEMANTIC_THRESHOLD` (0.75), **or** `heuristic_pass` (score still stored) |
| Distance | Jaro-Winkler distance < `JW_MAX_DISTANCE` (0.1) via `polars-distance` (heuristic passers kept even if JW ≥ cap) |

### Winner branches

Among stage-4 survivors:

- **Branch A** (any priced `price_per_kg`): lowest `price_per_kg`, JW similarity tie-break. Null-priced rows ignored for ranking.
- **Branch B** (all `price_per_kg` null): highest JW similarity (typical UNIDAD without weight).
- No survivors → `no_match`.

Null price/kg is never discarded from candidacy; it only changes which branch runs.

Then apply QuantityResolver on the winner.

---

## 7. Schemas

`ColumnsEnumBase` + `TableSchemaBase` (StrEnum, `list`, `dtypes`, `as_empty_dataframe`, `get_column_index`, `enforce_schema`).

Tables: `ProductTable`, `CandidateTable`, `LineResultTable`. No Pydantic for tables.

---

## 8. String distance

`polars-distance` `dist_str.jaro_winkler`. Not rapidfuzz / polars-strsim.

---

## 9. Promo policy

`PromoPolicy.effective_price(row, is_promo_member)`. Mercadona policy in v1; DIA/Carrefour stubs later. UI checkbox → worker `is_promo_member`.

---

## 10. Cold start and latency SLOs

**Warm worker** = container up + embedding model loaded. Free HF Spaces sleep when idle → first visit is usually cold (~container boot + ~100 MB model).

**Mitigation:** `POST /warmup`, model preload in FastAPI lifespan, Streamlit pre-warm on page load while the user pastes the list, honest UX copy, poll `/health` before enabling Match.

| Scenario | Target |
|----------|--------|
| Cold `/warmup` after idle | ≤ 90 s p95 |
| Hot 10-line job | ≤ 60 s p50 |
| Hot 50-line job | ≤ 5 min p95 (typical ~1–3 min) |
| Progress | always visible |

CPU is enough if catalog search is batched (Decision 13). If SLOs fail: batch/dedupe first, then smaller model, then paid CPU — not GPU by default.

### Measured (2026-08-17, mocked HTTP / sample catalog)

Offline only: `TokenOverlapEmbedder` (no MiniLM download), `SampleCatalogClient` **or** `MercadonaCatalogClient` with `httpx.MockTransport` serving `tests/fixtures/sample_catalog.json`. Courtesy sleep off (`sleep_s=0`). FastAPI `TestClient` (background job runs before return). Host: local Linux CPU. Tests: `tests/benchmark/test_job_latency_*.py`.

These numbers are **not** live Mercadona + MiniLM. They bound pipeline + parser cost. If mock p50 already blows past the caps below, the worker is too slow even without network.

| Scenario | Plan SLO | Measured | Mock fail / warn |
|----------|----------|----------|------------------|
| Cold `POST /warmup` (sample backend) | ≤ 90 s p95 (MiniLM + boot) | p50 **0.002 s**, p95 **0.003 s** (n=3) | fail > 5 s, warn > 1 s |
| Hot 10-line, sample catalog | ≤ 60 s p50 | cold 0.122 s; hot p50 **0.087 s**, p95 0.092 s (n=7) | fail p50 > 15 s, warn > 5 s |
| Hot 10-line, mocked Algolia | ≤ 60 s p50 | cold 0.093 s; hot p50 **0.093 s**, p95 0.094 s (n=7) | same |
| Hot 50-line, sample catalog | ≤ 5 min p95 (typical 1–3 min) | cold 0.427 s; hot p50 **0.414 s**, p95 0.421 s (n=5) | fail p50 > 60 s, warn > 20 s |
| Hot 50-line, mocked Algolia | ≤ 5 min p95 | cold 0.450 s; hot p50 **0.446 s**, p95 0.471 s (n=5) | same |

**Verdict:** mock path is well under SLOs. Live remaining cost is catalog RTT (batched) + MiniLM encode + Space cold boot — not linkage CPU. Chat 10 smoke is **one Algolia search**, not a full MiniLM job; do not treat 0.86 s as a hot-job SLO.

---

## 11. Large lists (50+)

Sequential HTTP would dominate. Levers:

1. Deduplicate normalized queries.
2. `search_batch` (chunks of ~100) — main lever.
3. Job progress `done/total`.
4. Soft warn at 50, hard reject at `MAX_LINES` (100).
5. Batch embeddings after all fetches.

Even at p95 5 min, careful manual price/kg shopping is ~25–45 min → still a large speedup. Drop the feature only if p50 regularly exceeds ~10 min on CPU.

---

## 12. Layout (OOP)

See `src/supermarket_linkage/`: `preprocessors/`, `catalog/`, `pipeline/`, `export/`, `validation/`, `worker/`, `app/`. Business logic not implemented in scaffold.

---

## 13. Testing

`tests/unit/`, `tests/integration/`, `tests/benchmark/`, `tests/fixtures/`. Semantic stage unit tests use fixed mock vectors (no model download in CI). Benchmarks: 10-line and 50-line latency. Live Algolia is opt-in only (`RUN_LIVE_MERCADONA=1`, marker `live`); default `pytest` skips it.

---

## 14. Threat model (v1)

**In scope:** megapaste, line spam, warmup/job spam, control-char paste, invalid postal code, open worker URL (`WORKER_API_KEY`), SSRF (fixed store URLs only), job TTL, ReDoS caps (`MAX_LINE_LENGTH` + simple regex), no full paste in logs, Mercadona rate courtesy.

**Out of scope:** botnets/DDoS, user accounts, cart-token GDPR flow (v2), formal pentest.

| Control | Value / note |
|---------|----------------|
| `MAX_LINES` | 100 |
| `WARN_LINES` | 50 |
| `MAX_LINE_LENGTH` | 200 |
| `MAX_TOTAL_BYTES` | 50_000 |
| `MAX_DUPLICATE_RATIO` | 0.95 |
| Warmup / jobs per IP | 10 / 5 per hour |
| Concurrent jobs per IP | 1 |
| `JOB_TIMEOUT_SECONDS` | 600 |
| `JOB_TTL_SECONDS` | 3600 |

Validate on the worker; Streamlit mirrors checks for UX only.


## Known limits

- Mercadona endpoints unofficial; may break.
- v1 export = links/CSV/clipboard; user adds items on the store site.
- DIA/Carrefour not implemented.
- UNIDAD without weight → Branch B (JW only).
- Job state lost on Space restart (no Redis yet).
- In-memory rate limits reset on restart; not botnet-proof.
