from __future__ import annotations

import sys
import time
from typing import List, Dict, Optional, Any
from datetime import timedelta
from pathlib import Path


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
    _RESULT_COLUMNS,
    _RESULT_COLUMN_LABELS,
    _STATUS_LABELS,
    _POLL_INTERVAL_S,
    _HEALTH_POLL_WHILE_COLD_S,
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
    defaults: Dict[str, Any] = {
        "list_text": "",
        "_uploaded_id": None,
        "worker_warm": False,
        "worker_sample": False,
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
    status_box = st.empty()
    bar = st.progress(0, text="En cola…")
    status_box.info("Emparejando… esto puede tardar unos segundos.")
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    not_found_streak = 0
    while time.monotonic() < deadline:
        try:
            body = client.get_job(job_id)
            not_found_streak = 0
        except WorkerError as exc:
            # Brief 404s can happen right after create or during a rolling deploy.
            if exc.status_code == 404 and not_found_streak < 6:
                not_found_streak += 1
                status_box.info("Preparando búsqueda…")
                time.sleep(_POLL_INTERVAL_S)
                continue
            raise
        prog = body.get("progress") or {}
        done = int(prog.get("done") or 0)
        total = int(prog.get("total") or 0)
        status = str(prog.get("status") or body.get("status") or "")
        label = _PROGRESS_LABELS.get(status, status)
        frac = min(1.0, done / total) if total else 0.0
        bar.progress(frac, text=f"{done}/{total} — {label}")
        status_box.info(f"Emparejando… {done}/{total} ({label})")
        job_status = str(body.get("status") or "")
        if job_status == "done":
            st.session_state.results = body.get("results") or []
            st.session_state.job_warnings = body.get("warnings") or []
            st.session_state.matched_count = body.get("matched_count")
            st.session_state.no_match_count = body.get("no_match_count")
            st.session_state.unmatched_queries = body.get("unmatched_queries") or []
            st.session_state.job_error = None
            status_box.empty()
            return
        if job_status in {"error", "timeout"}:
            st.session_state.job_error = body.get("error") or job_status
            st.session_state.results = None
            status_box.empty()
            return
        time.sleep(_POLL_INTERVAL_S)
    st.session_state.job_error = f"Tiempo de espera agotado ({JOB_TIMEOUT_SECONDS}s)."
    st.session_state.results = None
    status_box.empty()


def _health_poll_interval(worker_warm: bool) -> timedelta | None:
    """Poll /health only while cold. Continuous pings block Fly autostop."""
    if worker_warm:
        return None
    return timedelta(seconds=_HEALTH_POLL_WHILE_COLD_S)


def _render_worker_status(client: WorkerClient, worker_url: str) -> None:
    interval = _health_poll_interval(bool(st.session_state.get("worker_warm")))

    @st.fragment(run_every=interval)
    def _poll() -> None:
        if st.session_state.get("worker_warm"):
            sample = " (modo muestra)" if st.session_state.get("worker_sample") else ""
            st.success(f"Worker listo{sample}.")
            st.caption(
                "Si no hay búsquedas, el worker se apaga solo. "
                "La siguiente puede tardar un poco en arrancar."
            )
            return
        latest = client.health_or_none()
        now_warm = bool(latest and latest.get("warm"))
        prev = bool(st.session_state.get("worker_warm"))
        st.session_state.worker_warm = now_warm
        st.session_state.worker_sample = bool(latest and latest.get("use_sample_catalog"))
        if latest is None:
            st.info(f"Arrancando worker en `{worker_url}`…")
        elif now_warm:
            sample = " (modo muestra)" if st.session_state.worker_sample else ""
            st.success(f"Worker listo{sample}.")
        if now_warm != prev:
            st.rerun(scope="app")

    _poll()


def _render_results(
    rows: List[Dict[str, Any]],
    *,
    matched_count: Optional[int] = None,
    no_match_count: Optional[int] = None,
    unmatched_queries: Optional[List[str]] = None,
) -> None:
    st.subheader("Resultados")
    if matched_count is not None and no_match_count is not None:
        st.caption(f"{matched_count} emparejados · {no_match_count} sin emparejar")
    if unmatched_queries:
        preview = ", ".join(unmatched_queries[:8])
        more = f" (+{len(unmatched_queries) - 8})" if len(unmatched_queries) > 8 else ""
        st.info(f"Sin emparejar: {preview}{more}")

    display: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for col in _RESULT_COLUMNS:
            label = _RESULT_COLUMN_LABELS[col]
            value = row.get(col)
            if col == LineResultColumns.STATUS:
                value = _STATUS_LABELS.get(str(value or ""), value)
            elif col == LineResultColumns.PACK_SIZE_MISSING:
                if value is True:
                    value = "Sí"
                elif value is False:
                    value = "No"
            elif col == LineResultColumns.PRODUCT_URL:
                value = _EXPORT.product_url(row)
            item[label] = value
        display.append(item)

    column_config: dict[str, Any] = {}
    enlace_label = _RESULT_COLUMN_LABELS[LineResultColumns.PRODUCT_URL]
    if hasattr(st, "column_config"):
        column_config[enlace_label] = st.column_config.LinkColumn(
            enlace_label,
            help="Abre el producto en tienda.mercadona.es",
            display_text="Abrir en Mercadona",
            validate=r"^https://tienda\.mercadona\.es/.*",
        )
    st.dataframe(display, hide_index=True, use_container_width=True, column_config=column_config)

    st.subheader("Exportar lista")
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

    _render_worker_status(client, cfg.worker_url)

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
        help="Un producto por línea. Ejemplo: primera línea «arroz basmati 1500 g», segunda «leche entera 1l».",
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
        store_ok
        and validated is not None
        and validated.ok
        and postal_ok
    )
    if not st.session_state.worker_warm and can_match:
        st.caption("El worker puede estar apagado; la primera búsqueda tardará un poco más.")

    if st.button("Emparejar", type="primary", disabled=not can_match):
        assert validated is not None
        # Always start clean so a previous error / 404 cannot trap the UI.
        st.session_state.job_error = None
        st.session_state.results = None
        st.session_state.job_id = None
        with st.spinner("Enviando lista al worker…"):
            try:
                created = client.create_job(
                    text,
                    store=store_id,
                    postal_code=postal,
                    is_promo_member=is_promo_member,
                )
                st.session_state.job_id = created["id"]
                st.session_state.job_warnings = created.get("warnings") or []
                st.session_state.matched_count = None
                st.session_state.no_match_count = None
                st.session_state.unmatched_queries = []
            except WorkerError as exc:
                st.session_state.job_error = str(exc)

    job_id = st.session_state.get("job_id")
    if job_id and st.session_state.get("results") is None and not st.session_state.get(
        "job_error"
    ):
        try:
            _poll_job(client, job_id)
        except WorkerError as exc:
            st.session_state.job_error = str(exc)
            # Drop dead job id so Emparejar can run again without "Nueva lista".
            st.session_state.job_id = None
        st.rerun()

    if st.session_state.get("job_error"):
        st.error(st.session_state.job_error)
        st.caption("Puedes corregir la lista y pulsar Emparejar otra vez.")
        if st.button("Limpiar error"):
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
