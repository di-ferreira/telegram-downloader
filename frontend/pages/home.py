from __future__ import annotations

import pandas as pd
import streamlit as st

from components import ui
from core import paths, queries, registry, stats

source = ui.guard_source()
source_id = int(source["id"])

st.title("Biblioteca")
ui.source_header(source)

info = stats.overview(source)

metrics = st.columns(5)
metrics[0].metric("Mensagens", f"{info['messages']:,}")
metrics[1].metric("Mídias", f"{info['media']:,}")
metrics[2].metric("Tamanho", paths.human_size(info["bytes"]))
metrics[3].metric(
    "Assistidas",
    f"{info['watched']}/{info['tracked'] or 0}",
    delta=f"{info['watched_pct'] * 100:.0f}%",
)
metrics[4].metric("Arquivos ausentes", f"{info['missing']:,}")

tabs = st.tabs(["Visão geral", "Continuar", "Estrutura", "Execuções"])

# ------------------------------------------------------------- visão geral
with tabs[0]:
    monthly = stats.messages_per_month(source)
    if monthly:
        st.subheader("Mensagens por mês")
        st.line_chart(pd.DataFrame(monthly, columns=["mês", "mensagens"]).set_index("mês"))
    else:
        st.info("Sem dados de data para gráfico.")

    col_left, col_right = st.columns(2)
    if info["type_counts"]:
        with col_left:
            st.subheader("Por tipo")
            st.bar_chart(
                pd.DataFrame(
                    sorted(info["type_counts"].items(), key=lambda kv: -kv[1]),
                    columns=["tipo", "mensagens"],
                ).set_index("tipo"),
            )
    senders = stats.top_senders(source)
    if senders:
        with col_right:
            st.subheader("Principais remetentes")
            st.bar_chart(
                pd.DataFrame(senders, columns=["remetente", "mensagens"]).set_index("remetente")
            )

# --------------------------------------------------------------- continuar
with tabs[1]:
    in_progress = registry.list_progress(source_id, ("in_progress",), limit=12)
    if not in_progress:
        st.info("Nenhum vídeo em progresso. Assista algo na Galeria para retomar depois.")
    else:
        ids = [int(r["message_id"]) for r in in_progress if r.get("message_id")]
        rows = {int(r["id"]): r for r in queries.get_messages_by_ids(source, ids)}
        for state in in_progress:
            row = rows.get(int(state.get("message_id") or -1))
            if not row:
                continue
            percent = float(state.get("percent") or 0)
            label = row.get("file_name") or row.get("media_key") or f"msg {row.get('id')}"
            st.progress(min(percent, 1.0), text=f"{label} — {percent * 100:.0f}%")
            c1, c2, c3 = st.columns([6, 2, 2])
            with c2:
                if st.button("▶️ Continuar", key=f"cont_{row.get('id')}"):
                    st.session_state["detail_message_id"] = int(row.get("id"))
                    st.switch_page("pages/player.py")
            with c3:
                if st.button("Marcar assistido", key=f"done_{row.get('id')}"):
                    if row.get("media_key"):
                        registry.upsert_media_state(
                            source_id,
                            row["media_key"],
                            message_id=int(row.get("id")),
                            status="watched",
                            percent=1.0,
                            position_sec=float(state.get("duration_sec") or 0),
                            duration_sec=float(state.get("duration_sec") or 0),
                        )
                    st.rerun()

# ------------------------------------------------------------- estrutura
with tabs[2]:
    folders = stats.folder_sizes(source)
    if folders:
        st.subheader("Pastas de mídia")
        st.dataframe(
            pd.DataFrame(
                [
                    {"pasta": name, "arquivos": files, "tamanho": paths.human_size(total)}
                    for name, files, total in folders
                ]
            ),
            hide_index=True,
        )
    else:
        st.info("Nenhuma pasta `media/` encontrada nesta fonte.")

    st.subheader("Resumo")
    st.json(
        {
            "raiz": source.get("root_path"),
            "banco": source.get("db_path"),
            "json": source.get("json_path"),
            "canal": source.get("channel"),
            "ultimo_scan": source.get("last_scanned_at"),
            "mensagens": info["messages"],
            "midias": info["media"],
            "bytes": info["bytes"],
            "ausentes": info["missing"],
        },
        expanded=False,
    )

# -------------------------------------------------------------- execuções
with tabs[3]:
    jobs = registry.list_jobs(limit=10)
    if not jobs:
        st.info("Nenhuma execução registrada. Use **Backup & Restore**.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": job["id"],
                        "tipo": job["kind"],
                        "estado": job["status"],
                        "início": str(job.get("started_at") or "")[:19],
                        "fim": str(job.get("finished_at") or "")[:19],
                        "exit": job.get("exit_code"),
                    }
                    for job in jobs
                ]
            ),
            hide_index=True,
        )
