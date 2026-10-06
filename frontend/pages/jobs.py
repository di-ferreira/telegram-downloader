from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from components import ui
from config import MEDIA_TYPES, REPO_ROOT
from core import job_runner, registry

st.title("Backup & Restore")

jobs = registry.list_jobs(limit=20)
selected_job: dict | None = None


# ------------------------------------------------------------------ helpers


def _date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
        if value is None:
            return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _id_list(raw: str) -> list[int]:
    out: list[int] = []
    for chunk in (raw or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.append(int(chunk))
    return out


def _job_row(job: dict) -> dict:
    return {
        "id": job["id"],
        "tipo": job["kind"],
        "estado": job["status"],
        "início": str(job.get("started_at") or "")[:19],
        "fim": str(job.get("finished_at") or "")[:19],
        "exit": job.get("exit_code"),
    }


def _live_log(job: dict) -> None:
    job_id = int(job["id"])
    running = job.get("status") in ("running", "queued")
    if running:
        job = job_runner.refresh(job_id) or job

    status = job.get("status")
    st.caption(f"Job #{job_id} · **{status}** · pid `{job.get('pid') or '—'}`")

    if status in ("running", "queued") and job_runner.is_running(job_id):
        progress = job_runner.parse_progress(job_runner.read_tail(job_id, 8192))
        if progress.get("percent") is not None:
            st.progress(float(progress["percent"]), text=progress.get("message") or "...")
        elif progress.get("message"):
            st.caption(progress["message"])
    elif status == "failed":
        st.error(f"Falha (exit {job.get('exit_code')})")
    elif status == "succeeded":
        st.success("Concluído com sucesso.")
    elif status == "cancelled":
        st.warning("Cancelado.")
    elif status == "interrupted":
        st.warning("Interrompido (o processo morreu com a interface).")

    tail = job.get("log_tail") or job_runner.read_tail(job_id)
    st.code(tail[-8000:] or "(sem saída)", language="log")

    if st.button("⬇️ Baixar log completo", key=f"dl_{job_id}"):
        path = Path(job.get("log_path") or "")
        data = path.read_bytes() if path.exists() else tail.encode()
        st.download_button(
            "Salvar job_{}.log".format(job_id),
            data=data,
            file_name=f"job_{job_id}.log",
            mime="text/plain",
        )


# ------------------------------------------------------------------ formulários
left, right = st.columns(2)

with left:
    st.subheader("▶️ Executar backup")
    with st.form("backup_form"):
        b1, b2 = st.columns(2)
        with b1:
            start_date = st.date_input("De (data inicial)", value=None, key="bk_start")
        with b2:
            end_date = st.date_input("Até (data final)", value=None, key="bk_end")
        only_media = st.checkbox("Somente mídia", key="bk_only_media")
        only_text = st.checkbox("Somente texto", key="bk_only_text")
        media_type = st.selectbox(
            "Tipo de mídia", ["all", *MEDIA_TYPES], key="bk_media_type"
        )
        c1, c2 = st.columns(2)
        with c1:
            skip_existing = st.checkbox("Ignorar já existentes", value=True, key="bk_skip")
        with c2:
            resume = st.checkbox("Retomar de onde parou", value=True, key="bk_resume")
        message_ids = st.text_input(
            "IDs de mensagem (separados por vírgula)",
            key="bk_ids",
            placeholder="101, 202, 303",
            help="Deixe vazio para rodar sobre todo o intervalo.",
        )
        list_channels = st.checkbox("Listar canais disponíveis", key="bk_list")
        save_channels = st.checkbox("Salvar canais listados", key="bk_save")
        submitted_backup = st.form_submit_button("🚀 Iniciar backup", type="primary")

if submitted_backup:
    opts = {
        "only_media": only_media,
        "only_text": only_text,
        "start_date": _date(start_date),
        "end_date": _date(end_date),
        "media_type": media_type,
        "skip_existing": skip_existing,
        "resume": resume,
        "message_ids": _id_list(message_ids),
        "list_channels": list_channels,
        "save_channels": save_channels,
    }
    argv = job_runner.backup_argv(opts)
    job = job_runner.start_job("backup", argv, cwd=REPO_ROOT, opts=opts)
    if job.get("id"):
        st.session_state["selected_job"] = int(job["id"])
        st.success(f"Backup #{job['id']} iniciado.")
        st.rerun()
    else:
        st.error("Não foi possível iniciar o processo.")

with right:
    st.subheader("♻️ Executar restore")
    source = ui.current_source()
    default_backup = source.get("root_path") if source else str(REPO_ROOT / "downloads")
    with st.form("restore_form"):
        backup_folder = st.text_input(
            "Pasta do backup", value=default_backup, key="rs_folder"
        )
        r1, r2 = st.columns(2)
        with r1:
            r_start = st.date_input("De", value=None, key="rs_start")
        with r2:
            r_end = st.date_input("Até", value=None, key="rs_end")
        i1, i2 = st.columns(2)
        with i1:
            start_id = st.number_input("ID inicial", min_value=0, step=1, key="rs_id1")
        with i2:
            end_id = st.number_input("ID final", min_value=0, step=1, key="rs_id2")
        rc1, rc2 = st.columns(2)
        with rc1:
            r_only_media = st.checkbox("Somente mídia", key="rs_only_media")
        with rc2:
            r_only_text = st.checkbox("Somente texto", key="rs_only_text")
        r_type = st.selectbox("Tipo de mídia", ["all", *MEDIA_TYPES], key="rs_type")
        rc3, rc4 = st.columns(2)
        with rc3:
            retry_errors = st.checkbox("Repetir erros", key="rs_retry")
        with rc4:
            dry_run = st.checkbox("Simulação (dry-run)", value=True, key="rs_dry")
        channel_id = st.text_input(
            "Channel ID (apenas retry)", key="rs_channel", placeholder="-100..."
        )
        submitted_restore = st.form_submit_button("🚀 Iniciar restore", type="primary")

if submitted_restore:
    opts = {
        "backup_folder": backup_folder,
        "start_date": _date(r_start),
        "end_date": _date(r_end),
        "start_id": int(start_id) or None,
        "end_id": int(end_id) or None,
        "only_media": r_only_media,
        "only_text": r_only_text,
        "media_type": r_type,
        "retry_errors": retry_errors,
        "channel_id": channel_id or None,
        "dry_run": dry_run,
    }
    argv = job_runner.restore_argv(opts)
    job = job_runner.start_job("restore", argv, cwd=REPO_ROOT, opts=opts)
    if job.get("id"):
        st.session_state["selected_job"] = int(job["id"])
        st.success(f"Restore #{job['id']} iniciado.")
        st.rerun()
    else:
        st.error("Não foi possível iniciar o processo.")

# ------------------------------------------------------------------ histórico
st.markdown("---")
st.subheader("Histórico de execuções")

if not jobs:
    st.info("Nenhuma execução ainda.")
    st.stop()

table = pd.DataFrame([_job_row(j) for j in jobs])
event = st.dataframe(
    table,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="jobs_table",
)
sel = getattr(event, "selection", event)
selected_rows = list((sel.get("rows") if isinstance(sel, dict) else getattr(sel, "rows", None)) or [])
if selected_rows:
    st.session_state["selected_job"] = int(jobs[selected_rows[0]]["id"])

selected_id = st.session_state.get("selected_job")
if selected_id:
    for job in jobs:
        if int(job["id"]) == int(selected_id):
            selected_job = job
            break

if selected_job is None:
    selected_job = jobs[0]

st.markdown("---")
st.subheader(f"Log — job #{selected_job['id']}")


# Poll only while the selected job is still moving; a finished job is static.
_poll = 2.0 if selected_job.get("status") in ("running", "queued") else None


@st.fragment(run_every=_poll)
def _log_fragment() -> None:
    current = registry.get_job(int(selected_job["id"])) or selected_job
    _live_log(current)
    c1, c2 = st.columns([1, 4])
    with c1:
        if current.get("status") in ("running", "queued"):
            if st.button("🛑 Cancelar", key=f"cancel_{current['id']}"):
                job_runner.cancel(int(current["id"]))
                st.rerun()
        elif st.button("🔄 Atualizar", key=f"refresh_{current['id']}"):
            st.rerun()


_log_fragment()

# ------------------------------------------------------------------ ambiente
with st.expander("🔐 Variáveis do ambiente (.env) — valores mascarados"):
    preview = job_runner.env_preview(REPO_ROOT / ".env")
    if preview:
        st.json(preview, expanded=False)
    else:
        st.caption("Nenhum `.env` encontrado na raiz do repositório.")
    st.caption(
        "O processo roda em `cwd=<raiz do repositório>` e lê o `.env` sozinho; "
        "nenhuma credencial é exibida aqui."
    )
