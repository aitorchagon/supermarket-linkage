from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

# Slim Community Cloud install (app/requirements.txt) does not pip-install the
# package; keep `src/` on the path so this file still imports.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from supermarket_linkage.app.worker_client import (
    WorkerClient,
    start_warmup_once,
)
from supermarket_linkage.app.exceptions import WorkerError
from supermarket_linkage.app.master_config import (
    load_master_config,
    MasterConfig,
)
from supermarket_linkage.consts import (
    COMING_SOON_STORES,
    JOB_TIMEOUT_SECONDS,
    MAX_LINES,
    SUPPORTED_STORES,
    WARN_LINES,
)
from supermarket_linkage.schemas.line_result_table import LineResultColumns
from supermarket_linkage.validation.postal_code_validator import is_valid_postal_code
from supermarket_linkage.app.streamlit_consts import (
    _STORE_LABELS,
    _STORE_ORDER,
    _PROGRESS_LABELS,
    _COLD_START_MSG,
    _PRIVACY_MSG,
    _RESULT_COLUMNS,
    _POLL_INTERVAL_S,
    _VALIDATOR,
    _EXPORT,
)



def _config() -> MasterConfig:
    cfg = load_master_config()
    url, key = cfg.worker_url, cfg.api_key
    try:
        secrets = st.secrets
        secret_url = secrets.get("WORKER_URL")
        if secret_url:
            url = str(secret_url).rstrip("/")
        secret_key = secrets.get("WORKER_API_KEY")
        if secret_key:
            key = str(secret_key).strip() or None
    except FileNotFoundError:
        pass
    return MasterConfig(worker_url=url, api_key=key)


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "list_text": "",
        "_uploaded_id": None,
        "worker_warm": False,
        "job_id": None,
        "results": None,
        "job_error": None,
        "job_warnings": [],
        "matched_count": None,
        "no_match_count": None,
        "unmatched_queries": [],
        "store_id": "mercadona",
        "postal_code": "",
        "is_promo_member": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _apply_upload() -> None:
    """Optional .txt upload shown after the text area; reruns so the area updates."""
    uploaded = st.file_uploader("O sube un archivo .txt", type=["txt"])
    if uploaded is None:
        return
    file_id = f"{uploaded.name}:{uploaded.size}"
    if st.session_state.get("_uploaded_id") == file_id:
        return
    st.session_state["_uploaded_id"] = file_id
    st.session_state["list_text"] = uploaded.getvalue().decode("utf-8", errors="replace")
    st.rerun()


def _poll_job(client: WorkerClient, job_id: str) -> None:
    bar = st.progress(0, text="En cola…")
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        body = client.get_job(job_id)
        prog = body.get("progress") or {}
        done = int(prog.get("done") or 0)
        total = int(prog.get("total") or 0)
        status = str(prog.get("status") or body.get("status") or "")
        label = _PROGRESS_LABELS.get(status, status)
        frac = min(1.0, done / total) if total else 0.0
        bar.progress(frac, text=f"{done}/{total} — {label}")
        job_status = str(body.get("status") or "")
        if job_status == "done":
            st.session_state.results = body.get("results") or []
            st.session_state.job_warnings = body.get("warnings") or []
            st.session_state.matched_count = body.get("matched_count")
            st.session_state.no_match_count = body.get("no_match_count")
            st.session_state.unmatched_queries = body.get("unmatched_queries") or []
            st.session_state.job_error = None
            return
        if job_status in {"error", "timeout"}:
            st.session_state.job_error = body.get("error") or job_status
            st.session_state.results = None
            return
        time.sleep(_POLL_INTERVAL_S)
    st.session_state.job_error = f"Tiempo de espera agotado ({JOB_TIMEOUT_SECONDS}s)."
    st.session_state.results = None


@st.fragment(run_every=timedelta(seconds=2))
def _worker_status_fragment(client: WorkerClient, worker_url: str) -> None:
    latest = client.health_or_none()
    now_warm = bool(latest and latest.get("warm"))
    prev = bool(st.session_state.get("worker_warm"))
    st.session_state.worker_warm = now_warm
    if latest is None:
        st.error(
            f"No se puede conectar al worker en `{worker_url}`. "
            "Arráncalo en modo muestra: "
            "`USE_SAMPLE_CATALOG=1 uv run uvicorn supermarket_linkage.worker.api:app`"
        )
    elif now_warm:
        sample = " (modo muestra)" if latest.get("use_sample_catalog") else ""
        st.success(f"Worker listo{sample}.")
    else:
        st.info(_COLD_START_MSG)
    if now_warm != prev:
        st.rerun(scope="app")


def _render_results(
    rows: list[dict[str, Any]],
    *,
    matched_count: int | None = None,
    no_match_count: int | None = None,
    unmatched_queries: list[str] | None = None,
) -> None:
    st.subheader("Resultados")
    if matched_count is not None and no_match_count is not None:
        st.caption(f"{matched_count} con match · {no_match_count} sin match")
    if unmatched_queries:
        preview = ", ".join(unmatched_queries[:8])
        more = f" (+{len(unmatched_queries) - 8})" if len(unmatched_queries) > 8 else ""
        st.info(f"Sin match: {preview}{more}")

    display: list[dict[str, Any]] = []
    for row in rows:
        item = {col: row.get(col) for col in _RESULT_COLUMNS}
        # Always surface a trusted Mercadona URL (export builder), not a raw/empty cell.
        item[LineResultColumns.PRODUCT_URL] = _EXPORT.product_url(row)
        display.append(item)
    column_config: dict[str, Any] = {}
    if hasattr(st, "column_config"):
        column_config[LineResultColumns.PRODUCT_URL] = st.column_config.LinkColumn(
            "Enlace",
            help="Abre el producto en tienda.mercadona.es",
            display_text="Abrir en Mercadona",
            validate=r"^https://tienda\.mercadona\.es/.*",
        )
    st.dataframe(display, hide_index=True, use_container_width=True, column_config=column_config)

    st.subheader("Exportar lista")
    st.caption(
        "Enlaces públicos de la tienda, con cantidades. No inicia sesión ni escribe en el carrito."
    )
    csv_text = _EXPORT.to_csv(rows)
    clip = _EXPORT.to_clipboard_text(rows)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Descargar CSV",
            data=csv_text.encode("utf-8"),
            file_name="lista_mercadona.csv",
            mime="text/csv",
            key="dl_csv",
        )
    with c2:
        st.download_button(
            "Descargar enlaces (.txt)",
            data=clip.encode("utf-8"),
            file_name="lista_mercadona.txt",
            mime="text/plain",
            key="dl_txt",
        )
    st.text_area(
        "Texto con cantidades (copiar)",
        value=clip,
        height=180,
        key=f"clip_out_{st.session_state.get('job_id') or 'latest'}",
    )
    link_lines: list[str] = []
    for row in rows:
        url = _EXPORT.product_url(row)
        if not url:
            continue
        name = str(
            row.get(LineResultColumns.NAME) or row.get(LineResultColumns.QUERY) or "producto"
        ).replace("[", "(").replace("]", ")")
        link_lines.append(f"- [{name}]({url})")
    if link_lines:
        st.markdown("**Enlaces**\n\n" + "\n".join(link_lines))


def main() -> None:
    st.set_page_config(page_title="Lista → catálogo", page_icon="🛒", layout="wide")
    _init_state()
    cfg = _config()
    client = WorkerClient(cfg.worker_url, cfg.api_key)
    start_warmup_once(client)

    st.title("Lista de la compra → catálogo")
    st.caption(_PRIVACY_MSG)

    health = client.health_or_none()
    st.session_state.worker_warm = bool(health and health.get("warm"))
    _worker_status_fragment(client, cfg.worker_url)

    store_id = st.selectbox(
        "Tienda",
        options=list(_STORE_ORDER),
        format_func=lambda key: _STORE_LABELS.get(key, key),
        key="store_id",
    )
    store_ok = store_id in SUPPORTED_STORES
    if store_id in COMING_SOON_STORES:
        st.warning("Esta tienda estará disponible próximamente.")

    postal = st.text_input(
        "Código postal",
        max_chars=5,
        placeholder="28001",
        key="postal_code",
    ).strip()
    is_promo_member = st.checkbox(
        "Aplicar precios de club / promoción",
        key="is_promo_member",
        help="El worker usa el precio de oferta si el producto lo tiene. No requiere cuenta.",
    )

    text = st.text_area(
        "Lista de la compra (un producto por línea)",
        height=220,
        placeholder="arroz basmati 1500 g\nleche entera 1l",
        key="list_text",
    )
    _apply_upload()

    validated = _VALIDATOR.validate(text) if text.strip() else None
    if validated is not None:
        n = len(validated.lines) if validated.ok else 0
        if validated.ok:
            st.caption(f"{n} líneas (aviso a {WARN_LINES}, máximo {MAX_LINES}).")
        for warning in validated.warnings:
            st.warning(warning)
        if not validated.ok:
            st.error(validated.error)

    postal_ok = is_valid_postal_code(postal) if postal else False
    if postal and not postal_ok:
        st.error("El código postal debe ser exactamente 5 dígitos.")
    elif not postal:
        st.caption("El código postal fija el almacén y los precios.")

    can_match = (
        bool(st.session_state.worker_warm)
        and store_ok
        and validated is not None
        and validated.ok
        and postal_ok
    )

    if st.button("Emparejar", type="primary", disabled=not can_match):
        assert validated is not None
        try:
            created = client.create_job(
                text,
                store=store_id,
                postal_code=postal,
                is_promo_member=is_promo_member,
            )
            st.session_state.job_id = created["id"]
            st.session_state.job_warnings = created.get("warnings") or []
            st.session_state.results = None
            st.session_state.job_error = None
        except WorkerError as exc:
            st.error(str(exc))

    job_id = st.session_state.get("job_id")
    if job_id and st.session_state.get("results") is None and not st.session_state.get(
        "job_error"
    ):
        try:
            _poll_job(client, job_id)
        except WorkerError as exc:
            st.session_state.job_error = str(exc)
        st.rerun()

    if st.session_state.get("job_error"):
        st.error(st.session_state.job_error)
        if st.button("Nueva lista"):
            st.session_state.job_id = None
            st.session_state.job_error = None
            st.session_state.results = None
            st.rerun()

    results = st.session_state.get("results")
    if results is not None:
        for warning in st.session_state.get("job_warnings") or []:
            st.warning(warning)
        _render_results(
            results,
            matched_count=st.session_state.get("matched_count"),
            no_match_count=st.session_state.get("no_match_count"),
            unmatched_queries=st.session_state.get("unmatched_queries") or [],
        )
        if st.button("Nueva búsqueda"):
            st.session_state.job_id = None
            st.session_state.results = None
            st.session_state.job_error = None
            st.session_state.job_warnings = []
            st.session_state.matched_count = None
            st.session_state.no_match_count = None
            st.session_state.unmatched_queries = []
            st.rerun()


if __name__ == "__main__":
    main()
