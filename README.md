# record-linkage-supermarket-online

Paste a shopping list, pick a supermarket, get the best catalog match per line (price/kg when possible), how many packs you need, and exportable product links.

**v1:** Mercadona only. DIA and Carrefour are reserved in the UI/factory but not implemented.

Package import name: `supermarket_linkage`.

**Playwright is not required.** Mercadona uses `httpx` against hardcoded APIs. DIA/Carrefour are stubs (`NotImplementedError`). Do not install browsers or Playwright.

## Architecture

| Role | Where | Does |
|------|--------|------|
| Master | Streamlit (local, Community Cloud, or `docker compose`) | UI, submit, poll, export |
| Worker | FastAPI (local, Docker, or Hugging Face Spaces CPU) | catalog fetch, embeddings, pipeline, job API |

The Streamlit process never loads the embedding model and never calls Mercadona.

## Install (uv)

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
cp .env.example .env
```

Edit `.env` and set `WORKER_API_KEY` to a random string (do not commit `.env`).

## Sample vs live mode

| Mode | Flag | Worker behaviour |
|------|------|------------------|
| **Sample** (local default) | `USE_SAMPLE_CATALOG=1` | Fixture catalog + cheap token embedder. No Mercadona HTTP, no MiniLM download. |
| **Live** | `USE_SAMPLE_CATALOG=0` (or unset) | Mercadona HTTP + `paraphrase-multilingual-MiniLM-L12-v2` (~100 MB). CPU is enough. |

Sample catalog path defaults to `tests/fixtures/sample_catalog.json`. Override with `SAMPLE_CATALOG_PATH` if needed.

`SKIP_MODEL_PRELOAD=1` skips lifespan preload (tests). `/warmup` and the first job still lazy-load.

## Run locally (uv, sample)

The worker does not read `.env` by itself. `--env-file` injects `WORKER_API_KEY` (and sample/live flags) into both processes.

Terminal 1 — worker:

```bash
uv run --env-file .env uvicorn supermarket_linkage.worker.api:app --host 0.0.0.0 --port 8000
```

Terminal 2 — master (`WORKER_URL=http://localhost:8000` from `.env`):

```bash
uv run --env-file .env streamlit run src/supermarket_linkage/app/streamlit_app.py
```

## Docker Compose

Host ports: worker `8000` (container `7860`, HF Spaces convention), Streamlit `8501`.

```bash
cp .env.example .env   # set WORKER_API_KEY
docker compose up --build
```

Open http://localhost:8501. The Streamlit container talks to `http://worker:7860` (not `localhost`).

- **Sample:** leave `USE_SAMPLE_CATALOG=1` in `.env` (compose default).
- **Live:** `USE_SAMPLE_CATALOG=0 docker compose up --build` — first boot may take ~90 s (model download + load).

Compose interpolation reads `.env` in the project root. `WORKER_API_KEY` must match on both services.

## Secrets

Never commit real keys. `.env` is gitignored; `.env.example` is the template.

| Where | How |
|-------|-----|
| Local uv / compose | `.env`: `WORKER_URL`, `WORKER_API_KEY`, `USE_SAMPLE_CATALOG` |
| **Hugging Face Spaces** (worker) | Space **Settings → Secrets**: `WORKER_API_KEY`. Runtime env (not build-time). Unset key → worker is open — do not leave a public Space unprotected. |
| **Streamlit Community Cloud** (master) | App **Settings → Secrets** (TOML). The UI also reads `st.secrets`. |

Streamlit Community secrets example:

```toml
WORKER_URL = "https://<user>-<space>.hf.space"
WORKER_API_KEY = "the-same-random-string-as-the-space"
```

Local `.env` example (see `.env.example`):

```
WORKER_URL=http://localhost:8000
WORKER_API_KEY=change-me-to-a-random-string
USE_SAMPLE_CATALOG=1
```

## Hugging Face Spaces (worker)

Target hardware is **CPU Basic** (2 vCPU, 16 GB RAM, no GPU, no ZeroGPU). Playwright is not used.

Creating a **Docker** Space may require a paid HF plan (PRO / Team / Enterprise). CPU Basic is still the right runtime.

### Phase 2 — deploy checklist

**0. Push deploy files** (root `Dockerfile` must be on `main` before the Space builds):

```bash
git add Dockerfile
git commit -m "Add root Dockerfile for Hugging Face Spaces"
git push origin main
```

**1. Worker (Hugging Face Space)**

1. https://huggingface.co/new-space → SDK **Docker**, hardware **CPU Basic**, `app_port` **7860**.
2. Link this GitHub repo (`aitorchagon/supermarket-linkage`) or push the Space git remote to the same tree.
3. Space **Settings → Secrets**: `WORKER_API_KEY` = a long random string (same value you will put in Streamlit).
4. Space **Settings → Variables** (choose one mode):
   - **Production (live Mercadona):** do **not** set `USE_SAMPLE_CATALOG` (or set `0`).
   - **Demo only:** `USE_SAMPLE_CATALOG=1`.
5. Wait for the build. Open `https://<user>-<space>.hf.space/health` → expect `"status":"ok"`.
6. Warmup (replace URL and key):

```bash
curl -sS -X POST "https://<user>-<space>.hf.space/warmup" -H "X-API-Key: YOUR_KEY"
```

**2. Master (Streamlit Community Cloud)**

1. https://share.streamlit.io → New app → this GitHub repo, branch `main`.
2. Main file: `src/supermarket_linkage/app/streamlit_app.py`.
3. App **Settings → Secrets**:

```toml
WORKER_URL = "https://<user>-<space>.hf.space"
WORKER_API_KEY = "same-string-as-HF-Space-secret"
```

4. Deploy. Confirm the UI shows the worker as ready, then run a short list.

The slim file next to the app (`src/supermarket_linkage/app/requirements.txt`) keeps torch off Community Cloud.

---

## Hugging Face Spaces (worker) — details

Target hardware is **CPU Basic** (2 vCPU, 16 GB RAM, no GPU, no hourly charge). Do not pick GPU or ZeroGPU. Playwright is not used.

Creating a **Docker** Space requires a paid HF plan (PRO / Team / Enterprise). CPU Basic itself is still the right runtime: no CUDA torch, MiniLM fits in RAM.

1. Create a **Docker** Space (`sdk: docker`, `app_port: 7860`).
2. Repo root must contain `Dockerfile` (same as `Dockerfile.worker`; already in this repo for Spaces).
3. Push `Dockerfile`, `src/`, and `tests/fixtures/` (sample mode).
4. Hardware: **CPU Basic**.
5. Set **secret** `WORKER_API_KEY` (runtime env, not a public variable, not a Docker build-arg). For live Mercadona leave `USE_SAMPLE_CATALOG` unset; for a demo Space set variable `USE_SAMPLE_CATALOG=1`.
6. The container must listen on `0.0.0.0:7860` (`Dockerfile` / `Dockerfile.worker` already do).

CPU Basic Spaces sleep when idle. First visit is a cold start (container boot + ~100 MB model in live mode). The Streamlit UI pre-warms `POST /warmup` and polls `/health`.

Job state is in-memory: a Space restart drops in-flight jobs (Redis is deferred).

## Streamlit Community Cloud (master)

1. Deploy this repo. Main file: `src/supermarket_linkage/app/streamlit_app.py`.
2. Set secrets `WORKER_URL` (the Space URL) and `WORKER_API_KEY` (same string as the Space secret).
3. **Do not run embeddings on Community Cloud.** Cloud prefers `uv.lock` at the repo root, which would install torch. The slim file next to the app wins: `src/supermarket_linkage/app/requirements.txt` (streamlit, httpx, polars, numpy only).
4. Community Cloud does not start the worker. Point `WORKER_URL` at the Hugging Face Space (or another worker).

## Layout

- `src/supermarket_linkage/` — library (pipeline, catalog, worker, Streamlit master)
- `tests/` — unit, integration, benchmark, fixtures
- `Dockerfile.worker` / `Dockerfile.streamlit` / `docker-compose.yml` — packaging
- `DESIGN.md` — decisions (matching rules, Redis deferral, SLOs, threat model)

## Tests

```bash
uv sync --extra dev
# or, if uv is not installed: .venv/bin/python -m pytest
uv run pytest
```

Unit tests stay offline (mocked catalog / vectors). Default `pytest` does **not** call Mercadona.

Optional live Algolia smoke (one small search, courtesy sleep, not CI):

```bash
RUN_LIVE_MERCADONA=1 uv run pytest tests/integration/test_mercadona_live_smoke.py -s -v
```

Do not loop or hammer that test. See DESIGN.md § Live Mercadona smoke.

### GitHub Actions

Push or open a PR against `main` / `master`. Workflow: `.github/workflows/ci.yml`.

| Job | Gate | What |
|-----|------|------|
| Offline tests | **required** | `pytest` unit + integration + benchmark (`-m "not live"`) |
| Ruff | advisory (`continue-on-error`) | lint + format check until style debt is cleaned |

No automatic deploy yet (HF Spaces / Streamlit Cloud are configured in their UIs). Wire CD later with platform tokens if you want push-to-prod.
