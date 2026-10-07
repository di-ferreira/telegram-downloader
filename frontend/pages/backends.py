from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from components import ui
from config import MEDIA_TYPES, REPO_ROOT
from core import backend_state, content, envfile, job_runner, preflight, registry
from core.paths import human_size

st.title("🔌 Backends — backup e restore")
st.caption(
    "Descoberta de canais, artefatos do backup, simulação de restore e o "
    "progresso real do `restore_progress.db`. Tudo aqui **executa o backend** — "
    "as opções de conteúdo vivem em `Backup & Restore`."
)

# ------------------------------------------------------------ job ativo


def _dispatch(kind: str, opts: dict, purpose: str) -> None:
    if kind == "backup":
        checks = preflight.for_backup(opts) + preflight.validate_backup_opts(opts)
        argv = job_runner.backup_argv(opts)
    else:
        checks = preflight.for_restore(opts) + preflight.validate_restore_opts(opts)
        argv = job_runner.restore_argv(opts)

    failures = preflight.errors(checks)
    if failures:
        for item in failures:
            st.error(item["message"] + (f"\n\n`{item['fix']}`" if item.get("fix") else ""))
        ui.page_link("pages/config.py", label="Abrir Configurações", icon="⚙️")
        return

    job = job_runner.start_job(kind, argv, cwd=REPO_ROOT, opts=opts)
    if not job.get("id"):
        st.error("Não foi possível iniciar o processo.")
        return
    st.session_state["backend_job"] = {"id": int(job["id"]), "purpose": purpose}
    st.rerun()


_active = st.session_state.get("backend_job")
_poll = None
if _active:
    _row = registry.get_job(int(_active["id"])) or {}
    if _row.get("status") in ("running", "queued"):
        _poll = 2.0


@st.fragment(run_every=_poll)
def _active_job_fragment() -> None:
    active = st.session_state.get("backend_job")
    if not active:
        return
    job_id = int(active["id"])
    purpose = active.get("purpose")
    job = job_runner.refresh(job_id) or {}
    status = job.get("status")

    st.caption(f"Job #{job_id} · **{status}** · `{purpose}`")
    if status in ("running", "queued") and job_runner.is_running(job_id):
        progress = job_runner.parse_progress(job_runner.read_tail(job_id, 8192))
        if progress.get("percent") is not None:
            st.progress(float(progress["percent"]), text=progress.get("message") or "...")
        elif progress.get("message"):
            st.caption(progress["message"])

    if status in ("succeeded", "failed", "cancelled", "interrupted"):
        if purpose == "dry_run" and status == "succeeded":
            st.session_state["dry_run_result"] = backend_state.parse_dry_run(
                job_runner.read_tail(job_id, 1024 * 1024)
            )
        tail = job_runner.read_tail(job_id)
        with st.expander(f"Log do job #{job_id}"):
            st.code(tail[-6000:] or "(sem saída)", language="log")
        if status == "failed":
            st.error(f"Falha (exit {job.get('exit_code')}).")
        elif status == "succeeded":
            st.success("Concluído.")
        elif status == "cancelled":
            st.warning("Cancelado.")
        if st.button("🧹 Limpar", key="clear_active_job"):
            st.session_state.pop("backend_job", None)
            st.rerun()


_active_job_fragment()

# ----------------------------------------------------------------- canais
st.markdown("---")
st.subheader("📡 Canais acessíveis")

canais = backend_state.saved_channels()
if canais:
    table = pd.DataFrame(canais)
    st.dataframe(table, hide_index=True, width="stretch")
    opcoes = {
        f"{row['title'] or '(sem título)'} · {row['username']} · {row['id']}": row["id"]
        for row in canais
    }
    escolhido = st.selectbox("Usar como CHANNEL", list(opcoes), key="pick_channel")
    if st.button("✅ Gravar CHANNEL no `.env`", key="apply_channel"):
        envfile.write({"CHANNEL": opcoes[escolhido]})
        st.success(f"CHANNEL = {opcoes[escolhido]}")
        st.rerun()

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("📡 Listar canais agora", key="run_list_channels"):
        _dispatch("backup", {"list_channels": True, "save_channels": True}, "channels")
with col_b:
    st.caption(
        "Roda `backup.py --list-channels --save` e grava `backup/channels.txt` "
        "(já ignorado pelo git)."
    )

# ------------------------------------------------------------- artefatos
st.markdown("---")
st.subheader("📦 Saídas do backup")

saida = backend_state.output_dir()
st.caption(f"OUTPUT_DIR → `{saida}`")

artefatos = backend_state.backup_artifacts()
linhas = [
    {
        "arquivo": row["label"],
        "existe": "sim" if row["exists"] else "—",
        "tamanho": human_size(row["size"]) if row["size"] is not None else "—",
        "detalhe": row["detail"] or "",
    }
    for row in artefatos
]
st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")

log_path = saida / "log.txt"
if log_path.exists() and st.checkbox("Ver tail de `log.txt`", key="show_backup_log"):
    st.code(backend_state.read_tail(log_path), language="log")

detectado = content.detect(saida)
tem_backup = bool(detectado.get("db_path") or detectado.get("json_path"))
existente = registry.get_source_by_root(detectado["root_path"]) if tem_backup else None

if not tem_backup:
    st.info("Nenhum `backup.db`/`messages.json` nesta pasta ainda — rode um backup.")
else:
    c1, c2 = st.columns(2)
    with c1:
        if existente:
            if st.button("🔄 Re-escanear fonte no índice", key="rescan_output"):
                with st.spinner("Indexando..."):
                    content.scan_source(int(existente["id"]))
                st.success(
                    f"{existente.get('message_count', 0)} mensagens no índice."
                )
                st.rerun()
        elif st.button("➕ Registrar como fonte", type="primary", key="add_output"):
            nova = registry.add_source(
                root_path=detectado["root_path"],
                name=Path(detectado["root_path"]).name,
                channel=envfile.get("CHANNEL") or None,
                db_path_=detectado.get("db_path"),
                json_path=detectado.get("json_path"),
            )
            if nova:
                with st.spinner("Indexando..."):
                    content.scan_source(int(nova["id"]))
                st.success("Fonte cadastrada e indexada.")
                st.rerun()
    with c2:
        if existente:
            st.caption(
                f"Já é a fonte **#{existente['id']}** · "
                f"{existente.get('message_count', 0):,} mensagens indexadas."
            )

# --------------------------------------------------------------- dry-run
st.markdown("---")
st.subheader("🧪 Simular restore (dry-run)")

st.caption(
    "`--dry-run` não abre sessão nem publica nada: lê o backup e imprime estatísticas."
)
d1, d2 = st.columns([1, 1])
with d1:
    dry_folder = st.text_input(
        "Pasta do backup",
        value=str(envfile.backup_folder()),
        key="dry_folder",
    )
with d2:
    dry_type = st.selectbox("Tipo de mídia", ["all", *MEDIA_TYPES], key="dry_type")

if st.button("🧪 Rodar simulação", key="run_dry"):
    _dispatch(
        "restore",
        {"backup_folder": dry_folder, "media_type": dry_type, "dry_run": True},
        "dry_run",
    )

resultado = st.session_state.get("dry_run_result")
if resultado:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mensagens", f"{resultado['total']:,}")
    m2.metric("Com mídia", f"{resultado['with_media']:,}")
    m3.metric("Só texto", f"{resultado['text_only']:,}")
    m4.metric("Mídia ausente", f"{resultado['missing']:,}")
    st.caption(f"Tamanho da mídia: {resultado['size_label']}")
    if resultado["missing_files"]:
        st.warning(
            f"{len(resultado['missing_files'])} arquivo(s) ausente(s) — não seriam restaurados:"
        )
        st.code("\n".join(resultado["missing_files"][:50]), language="text")
elif "dry_run_result" in st.session_state:
    st.info("Não consegui interpretar a saída do dry-run; veja o log do job acima.")

# ------------------------------------------------------- progresso restore
st.markdown("---")
st.subheader("📊 Progresso do restore")

progresso = backend_state.restore_progress()
if not progresso["total"]:
    st.info("Nenhum `restore_progress.db` ainda — nenhum restore executou por aqui.")
else:
    counts = progresso["counts"]
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Enviadas", counts.get("sent", 0))
    p2.metric("Erros", counts.get("error", 0))
    p3.metric("Ignoradas", counts.get("skipped", 0))
    p4.metric("Total registrado", progresso["total"])
    if progresso.get("last_sent"):
        st.caption(f"Última mensagem enviada: id `{progresso['last_sent']}` (retomada automática).")

    if progresso["errors"]:
        st.markdown("**Mensagens com erro**")
        st.dataframe(pd.DataFrame(progresso["errors"]), hide_index=True, width="stretch")

        erro = progresso["errors"][0]
        st.warning(
            "Repetir erros publica de verdade (sem dry-run) e precisa do canal de destino."
        )
        r1, r2 = st.columns([2, 1])
        with r1:
            retry_channel = st.text_input(
                "Channel ID/username de destino",
                value=envfile.get("CHANNEL"),
                key="retry_channel",
            )
        with r2:
            st.caption("Ex.: `-1001234567890` ou `@canal`")
        if st.button("🔁 Repetir apenas os erros", key="run_retry"):
            _dispatch(
                "restore",
                {
                    "backup_folder": str(envfile.backup_folder()),
                    "retry_errors": True,
                    "channel_id": retry_channel.strip(),
                    "dry_run": False,
                },
                "retry",
            )

# ------------------------------------------------------------------ logs
st.markdown("---")
st.subheader("🗂️ Logs do restore")

logs = backend_state.restore_logs()
disponiveis = {label: path for label, path in logs.items() if path.exists()}
if not disponiveis:
    st.caption(
        f"Nada em `{logs['restore'].parent}` — os logs são gravados em "
        "`logs/` durante a execução (relativo à raiz do repositório)."
    )
else:
    rotulo = st.selectbox("Arquivo", list(disponiveis), key="restore_log_pick")
    path = disponiveis[rotulo]
    st.code(backend_state.read_tail(path), language="log")
    st.download_button(
        f"⬇️ Baixar {path.name}",
        data=path.read_bytes(),
        file_name=path.name,
        mime="text/plain",
        key="dl_restore_log",
    )
