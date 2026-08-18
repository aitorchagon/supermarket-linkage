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
| Semantic | Cosine ≥ `SEMANTIC_THRESHOLD` (0.75) |
| Distance | Jaro-Winkler distance < `JW_MAX_DISTANCE` (0.1) via `polars-distance` |

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

---

## 15. Implementation order (agent chats)

One **new Agent chat** per Chat N. Do not reuse the previous Agent chat. After Chat N, open a new **Ask** chat and paste the matching **Review** prompt. If Review finds issues, a new Agent chat with the **Fix** template.

**Done when** the tests listed for that chat pass. Do not start Chat N+1 until Chat N is done.

| Chat | Agent does | Done when (tests) | Status |
|------|------------|-------------------|--------|
| 1 | Scaffold: `pyproject.toml`, consts, schemas, this DESIGN.md | Layout exists; no business logic | **done** |
| 2 | Input anti-abuse + rate limiter | `tests/unit/test_input_validator.py`, `test_rate_limiter.py` | **done** |
| 3 | Preprocessors + QuantityResolver | `test_text_normalizer.py`, `test_price_normalizer.py`, `test_quantity_resolver.py` | **done** |
| 4 | Rule-based pipeline (offline) | unit tests per stage + `test_winner_selection.py` + `tests/integration/test_pipeline_sample_catalog.py` | **done** |
| 5 | Mercadona client + promo + factory stubs | `test_mercadona_parser.py`, `test_promo_policy.py` (fixtures, no live HTTP) | **next** |
| 6 | Worker FastAPI (`/health`, `/warmup`, `/jobs`) | TestClient: 400 / 429 / happy path with mocked catalog | pending |
| 7 | Streamlit master + export | `test_export_builder.py`; UI talks to local worker in sample mode | pending |
| 8 | Docker + deploy files | `docker-compose` documented and coherent | pending |
| 9 | Latency benchmarks 10-line / 50-line | `tests/benchmark/test_job_latency_*.py`; SLOs written here | **done** |
| 10 | Optional live Mercadona smoke | Opt-in `RUN_LIVE_MERCADONA=1`; one small search or documented failure | **done** |

**How to run:** new Agent chat → paste the Chat N prompt below → `@DESIGN.md`. After it stops → new Ask chat → Review N. Model: **Auto**, unless noted.

---

## 16. Agent prompts

Copy the fenced block into a **new Agent chat**. Attach this file.

### Chat 1 — Scaffold (Agent · Auto) — done

```
You are implementing ONLY scaffold for record-linkage-supermarket-online.

Read: DESIGN.md (Decisions 1–14). Do NOT implement pipeline, Mercadona client, Streamlit, or worker APIs yet.

Workspace: /home/aitorchagon/Desktop/Proyectos/record-linkage-dia-online
Optionally rename folder conceptually in docs to record-linkage-supermarket-online; if renaming the directory is awkward, keep the path and set package name record-linkage-supermarket-online / supermarket_linkage.

Create:
1. pyproject.toml (uv-style, hatchling, python>=3.11, deps: polars, polars-distance, httpx, fastapi, uvicorn, streamlit, sentence-transformers, torch, numpy; optional-dev: pytest, pytest-httpx, pytest-asyncio, ruff)
2. .env.example (WORKER_URL, WORKER_API_KEY, DEFAULT_WAREHOUSE)
3. .gitignore (venv, .env, __pycache__, .pytest_cache, uv.lock optional keep)
4. DESIGN.md — seed from plan decisions (numbered, why/why-not, Redis deferral, cold start, large lists, threat model, export/GDPR, winner branches, latency SLOs). Docstring style: short, direct, not LLM fluff.
5. Package src/supermarket_linkage/ with:
   - __init__.py
   - consts.py (thresholds, limits, Mercadona URL constants, stores)
   - regex_consts.py (POSTAL_CODE, QUANTITY, PACK_SIZE, CONTROL_CHARS, NON_WORD — simple patterns only)
   - schemas/base.py — ColumnsEnumBase + TableSchemaBase EXACTLY as in the plan (StrEnum, list, dtypes, as_empty_dataframe, get_column_index, enforce_schema)
   - schemas/product_table.py, candidate_table.py, line_result_table.py (columns + dtypes only; include units_needed / price fields from plan)
   - Empty __init__.py packages for: preprocessors, catalog, pipeline, export, validation, worker, app
6. README.md — short: what it is, how to install with uv, that Mercadona is v1 only
7. tests/ placeholders: tests/unit/, tests/integration/, tests/benchmark/, tests/fixtures/ (can be empty dirs with .gitkeep)

STOP when layout exists and DESIGN.md is written. Do not implement business logic. Do not run live network calls. Do not add Redis/Playwright/rapidfuzz.
```

#### Review 1 (Ask)

```
Review ONLY the scaffold for plan drift.
Check: TableSchemaBase matches plan; consts thresholds (SEMANTIC 0.75, JW 0.1, MAX_LINES 100); DESIGN.md covers store selector, Redis, cold start, 50-line batch, threat model, export v1 vs v2, winner Branch A/B.
List concrete file:line issues. Do not rewrite files. Suggest a minimal fix list for the next Agent chat.
```

---

### Chat 2 — Input validation + rate limiter (Agent · Auto) — done

```
DESIGN.md Continue from DESIGN.md and existing scaffold. Implement ONLY input anti-abuse (Decision 14).

Implement:
- src/supermarket_linkage/validation/input_validator.py
- src/supermarket_linkage/validation/postal_code_validator.py (or same module if tiny)
- src/supermarket_linkage/worker/rate_limiter.py (in-process per-IP token bucket; constants from consts.py)
- tests/unit/test_input_validator.py
- tests/unit/test_rate_limiter.py

Rules from DESIGN/consts: MAX_LINES 100, WARN_LINES 50, MAX_LINE_LENGTH 200, MAX_TOTAL_BYTES 50000, MAX_DUPLICATE_RATIO 0.95, postal ^\d{5}$, strip control chars, skip empty lines.
Rate limits: warmup 10/h, jobs 5/h, max 1 concurrent job per IP.
OOP only if needed (simple classes OK). Clear docstrings, your style: short, pre/post, no fluff.
Do not implement Streamlit, FastAPI routes, or Mercadona.
Run unit tests for these modules if possible. STOP when tests pass (or document why they can't run).
```

#### Review 2 (Ask)

```
Review validation/ and rate_limiter/ vs Decision 14. Check limits, duplicate spam, postal validation, no logging of full paste. List minimal fixes only.
```

---

### Chat 3 — Preprocessors + QuantityResolver (Agent · Auto) — done

```
DESIGN.md Continue from DESIGN.md. Implement ONLY preprocessors.

Implement:
- preprocessors/base_preprocessor.py (ABC process(df)->df)
- preprocessors/text_normalizer.py (lowercase, accents, stopwords, extract search query, parse requested quantity using regex_consts)
- preprocessors/price_normalizer.py (KILO/LITRO/UNIDAD, approx weight from name, price_per_kg; null when unknown)
- preprocessors/quantity_resolver.py (ceil(requested/pack); min 1; 1500g vs 1kg → 2)
- tests/unit/test_text_normalizer.py
- tests/unit/test_price_normalizer.py
- tests/unit/test_quantity_resolver.py

Use Polars + TableSchemaBase.enforce_schema where useful. No pipeline stages, no Mercadona, no Streamlit.
STOP when unit tests pass for these modules.
```

#### Review 3 (Ask)

```
Review quantity math and unit conversion (g/kg, ml/L). Flag edge cases: missing pack size → units_needed=1 with warning. Minimal fix list only.
```

---

### Chat 4 — Pipeline + LinkageOrchestrator (Agent · Auto; upgrade model only if tests fail twice) — done

```
DESIGN.md Continue from DESIGN.md. Implement ONLY the rule-based linkage pipeline (offline).

Implement:
- pipeline/base_stage.py
- pipeline/heuristic_stage.py (exact normalized OR all query tokens in name)
- pipeline/blocking_stage.py (same source_query)
- pipeline/semantic_stage.py (cosine >= 0.75; injectable embedder for tests — mock vectors in unit tests, no model download in CI)
- pipeline/distance_stage.py (polars-distance dist_str.jaro_winkler; JW distance < 0.1)
- pipeline/linkage_orchestrator.py (chain stages; winner Branch A priced → lowest price_per_kg then JW; Branch B all null → highest JW; then QuantityResolver)
- tests/unit/ for each stage + test_winner_selection.py
- data/sample_catalog.json (~30–50 Mercadona-shaped products) OR tests/fixtures/sample_catalog.json
- tests/integration/test_pipeline_sample_catalog.py

No weighted scores. No live HTTP. No FastAPI/Streamlit.
STOP when unit + integration tests pass offline.
```

#### Review 4 (Ask)

```
Review pipeline against Decisions 6 and winner Branch A/B. Confirm semantic threshold 0.75 and JW distance < 0.1 (not similarity confused). Check mocks avoid downloading models in tests. Minimal fixes only.
```

---

### Chat 5 — Mercadona client + promo (Agent · Auto) — next

```
DESIGN.md Continue from DESIGN.md. Implement ONLY catalog client for Mercadona (fixtures first, no live calls required for tests).

Implement:
- catalog/base_catalog_client.py (search, search_batch → ProductTable)
- catalog/promo_policy.py (ABC) + MercadonaPromoPolicy (promo price only if is_promo_member)
- catalog/catalog_client_factory.py (mercadona enabled; dia/carrefour raise NotImplementedError)
- catalog/mercadona_client.py (httpx; hardcoded base URLs only — no SSRF; search_batch; postal→warehouse; rate courtesy sleep)
- catalog/dia_client.py and carrefour_client.py stubs (NotImplementedError)
- tests/fixtures/mercadona_search_response.json (+ detail if needed)
- tests/unit/test_mercadona_parser.py, test_promo_policy.py
- Use pytest-httpx or fixture parsing only in tests

Do not implement worker API or Streamlit. Do not scrape DIA. STOP when parser/promo unit tests pass.
```

#### Review 5 (Ask)

```
Review Mercadona client for: hardcoded URLs only, batch search design, promo toggle behavior, factory stubs. Suggest minimal fixes. Do not expand to live E2E yet.
```

---

### Chat 6 — Worker API (Agent · Auto)

```
DESIGN.md Continue from DESIGN.md. Implement ONLY the worker FastAPI service.

Implement:
- worker/job_store.py (InMemoryJobStore + JobStore ABC; TTL JOB_TTL_SECONDS; Redis migration noted in comments/DESIGN only)
- worker/job_orchestrator.py (validate → dedupe → search_batch → linkage → progress updates; JOB_TIMEOUT_SECONDS; do not log full paste)
- worker/warmup.py + lifespan model preload (lazy-load OK if documented)
- worker/api.py: GET /health, POST /warmup, POST /jobs, GET /jobs/{id}
  - Optional WORKER_API_KEY header check
  - Wire InputValidator + RateLimiter
  - Progress: {done, total, status}
- Minimal entrypoint so `uvicorn supermarket_linkage.worker.api:app` works
- Light tests if easy (TestClient) for validation 400 / rate limit 429 / happy path with mocked catalog

Do not implement Streamlit UI. Prefer sample catalog / mocked client when USE_SAMPLE_CATALOG=1 for local tests.
STOP when health/warmup/jobs work locally with sample mode.
```

#### Review 6 (Ask)

```
Review worker API: auth header, rate limits, job TTL, progress shape, no paste in logs, master/worker separation. Minimal fixes only.
```

---

### Chat 7 — Streamlit master + export (Agent · Auto)

```
DESIGN.md Continue from DESIGN.md. Implement ONLY Streamlit master UI + export.

Implement:
- export/base_export_builder.py + mercadona_export_builder.py (product URLs, CSV, clipboard text with units_needed)
- app/streamlit_app.py:
  - Store selectbox: Mercadona enabled; DIA/Carrefour "Próximamente" disabled
  - Postal code, promo/club checkbox
  - Paste + optional txt upload
  - Client-side mirror of InputValidator limits
  - Pre-warm: POST /warmup on load; poll /health; honest cold-start message
  - Submit job with WORKER_URL + WORKER_API_KEY; poll progress bar
  - Results table + Exportar lista (CSV/links)
- tests/unit/test_export_builder.py

Do not change pipeline logic. STOP when UI can talk to local worker in sample mode.
```

#### Review 7 (Ask)

```
Review Streamlit UX vs plan: store selector, pre-warm, progress, export without login, promo toggle passed to worker. Minimal fixes only.
```

---

### Chat 8 — Docker + deploy files (Agent · Auto)

```
DESIGN.md Continue from DESIGN.md. Implement ONLY packaging/deploy files.

Create:
- docker-compose.yml (streamlit + worker)
- Dockerfile.worker (HF Spaces CPU-friendly)
- Dockerfile.streamlit if needed
- Update README with: uv sync, playwright NOT required, how to set secrets, HF Spaces + Streamlit Community notes, sample vs live mode
- .env.example already exists — keep in sync

Do not redesign architecture. STOP when docker-compose is documented and coherent.
```

#### Review 8 (Ask)

```
Review Docker/README for free-tier CPU assumptions, WORKER_API_KEY wiring, and that Streamlit does not run embeddings. Minimal fixes only.
```

---

### Chat 9 — Benchmarks (Agent · Auto) — done

```
DESIGN.md Continue from DESIGN.md. Implement ONLY latency benchmarks (mocked HTTP / sample catalog).

Create:
- tests/benchmark/test_job_latency_10_lines.py
- tests/benchmark/test_job_latency_50_lines.py
Document results in DESIGN.md § Latency (cold vs hot SLOs from plan). Fail or warn if p50 wildly exceeds targets with mocks (set pragmatic thresholds).

Do not add ZeroGPU. STOP when benchmarks run and DESIGN.md is updated.
```

#### Review 9 (Ask)

```
Review benchmark methodology: are HTTP mocks fair? Are SLOs interpreted as typical vs p95? Any next optimization steps if slow?
```

---

### Optional Chat 10 — Live Mercadona smoke (Agent · Auto · last) — done

```
ONLY if fixtures path works. Add a documented, opt-in live smoke test or CLI script gated by RUN_LIVE_MERCADONA=1.
Respect rate limits. Do not hammer Algolia. Update DESIGN with what broke/worked.
STOP after one successful small live search OR documented failure with next steps.
```

---

### Fix template (Agent · any milestone)

```
Apply ONLY these fixes from Ask review. Do not refactor unrelated code. Do not expand scope.

Fixes:
- <paste bullet list from Ask review>

Run the relevant unit tests. STOP when fixed.
```

---

## 17. Suggested model map

| Chat | Model |
|------|-------|
| 1–3, 6–9 | Auto |
| 4 (pipeline) | Auto first; if winner/JW/tests fail twice → stronger model for **Fix** only |
| 5 (Mercadona) | Auto first; stronger model only if Algolia/parser stuck |
| Reviews | Ask mode |

---

## 18. Success criteria (v1 complete)

- Store selector visible; only Mercadona enabled in v1
- `/warmup` pre-loads model; Streamlit pre-warms on page open
- `arroz basmati 1500 g` → matches 1 kg pack, `units_needed = 2`
- Branch A: priced candidates ranked by lowest price/kg; Branch B: all-null → highest JW
- **10-line** hot job ≤ 60 s; **50-line** hot job ≤ 5 min (benchmarks in this file)
- Progress bar shows `done/total` during long jobs
- Input validator rejects megapaste / line spam; rate limiter returns 429 on abuse
- Export produces openable product URLs with quantities — no login required
- Promo toggle changes `effective_price` when promo fields exist
- Postal code changes warehouse and prices
- All unit tests pass offline; integration test passes on sample catalog

---

## Live Mercadona smoke (Chat 10)

Gate: fixture parser tests must pass first (`tests/unit/test_mercadona_parser.py`, `test_promo_policy.py` — 22 passed, 2026-08-17). Live HTTP is **not** in the default suite.

**How (once, not CI, do not loop):**

```bash
RUN_LIVE_MERCADONA=1 uv run pytest tests/integration/test_mercadona_live_smoke.py -s -v
```

Test: `MercadonaCatalogClient(warehouse="mad1", hits_per_page=5).search("arroz")` — one Algolia POST, no postal PUT, default courtesy sleep (`HTTP_RATE_LIMIT_SECONDS` = 0.5 s). Without `RUN_LIVE_MERCADONA=1` the test is skipped.

### Result (2026-08-17, one attempt)

| | |
|--|--|
| Outcome | **worked** (pytest PASSED, 0.86 s including sleep) |
| Hits | 5 (capped by `hits_per_page`) |
| First row | `product_id=5044`, name `Arroz redondo Hacendado Paquete` |
| Parser | live JSON still maps: `id`, `display_name`/`packaging`, `share_url` on `tienda.mercadona.es` |
| Auth / UA | no 401/403; hardcoded search-only Algolia key + host were enough (no extra User-Agent) |
| Not exercised | postal→warehouse PUT; MiniLM / full job; DIA/Carrefour |

**What did not break:** unofficial Algolia host, index `products_prod_mad1_es`, and hit shape still match the client.

**Next steps (only if this starts failing):** capture status + response body (redact keys); if 403, try a browser-like User-Agent on the existing hardcoded hosts only; if 200 but empty/unparsed rows, diff live JSON vs `tests/fixtures/mercadona_search_response.json` and update `parse_hit`. Do not retry in a tight loop.

---

## Known limits

- Mercadona endpoints unofficial; may break.
- v1 export = links/CSV/clipboard; user adds items on the store site.
- DIA/Carrefour not implemented.
- UNIDAD without weight → Branch B (JW only).
- Job state lost on Space restart (no Redis yet).
- In-memory rate limits reset on restart; not botnet-proof.
