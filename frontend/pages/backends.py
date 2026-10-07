from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from components import filters as flt, ui
from config import MEDIA_TYPES, REPO_ROOT
from core import backend_state, channels, content, envfile, job_runner, preflight, registry
from core.paths import human_size

st.title("🔌 Backends — backup e restore")
st.caption(
    "Descoberta de canais, artefatos do backup, simulação de restore e o "
    "progresso real do `restore_progress.db`. Tudo aqui **executa o backend** — "
    "as opções de conteúdo vivem em `Backup & Restore`."
)

# ------------------------------------------------------------ job ativo


def _dispatch(
    kind: str,
    opts: dict,
    purpose: str,
    env_extra: dict[str, str] | None = None,
) -> None:
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

    job = job_runner.start_job(kind, argv, cwd=REPO_ROOT, opts=opts, env_extra=env_extra)
    if not job.get("id"):
        st.error("Não foi possível iniciar o processo.")
        return
    st.session_state["backend_job"] = {"id": int(job["id"]), "purpose": purpose}
    st.rerun()


# ------------------------------------------------------------ download


def _download(row: dict) -> None:
    """Grava ``CHANNEL``/``OUTPUT_DIR`` no ``.env`` e dispara o backup do canal."""
    values, folder = channels.prepare(row)
    envfile.write(values)
    _dispatch(
        "backup",
        {
            "resume": True,
            "channel_id": str(row.get("id") or ""),
            "channel_title": row.get("title") or "",
        },
        "channel_download",
        env_extra={
            "CHANNEL": values["CHANNEL"],
            "OUTPUT_DIR": str(folder),
            "OUTPUT_BASE": str(envfile.output_base()),
        },
    )


def _register_download(args: dict) -> None:
    """Ao concluir um download: registra a pasta como fonte e indexa o canal."""
    channel_id = str(args.get("channel_id") or "")
    row = next((r for r in channels.rows() if str(r.get("id")) == channel_id), None)
    if row is None:
        return
    label = row.get("title") or channel_id
    try:
        source = channels.ensure_source(row)
        if not source:
            st.session_state["channels_download_error"] = (
                f"Pasta de `{label}` não tem `backup.db` nem `messages.json`."
            )
            return
        if not source.get("last_scanned_at"):
            with st.spinner(f"Indexando `{label}`..."):
                channels.scan(source)
        st.session_state["source_id"] = int(source["id"])
        st.session_state["channels_download_ready"] = label
    except Exception as exc:  # noqa: BLE001 - quebrar a página aqui esconderia o log
        st.session_state["channels_download_error"] = f"`{label}`: {exc}"


_active = st.session_state.get("backend_job")
_poll = None
_row: dict = {}
_args: dict = {}
if _active:
    _row = registry.get_job(int(_active["id"])) or {}
    if _row.get("status") in ("running", "queued"):
        _poll = 2.0
    try:
        _args = json.loads(_row.get("args") or "{}")
    except (TypeError, ValueError):
        _args = {}

_purpose = (_active or {}).get("purpose")
_downloading_id = str(_args.get("channel_id") or "") if _purpose == "channel_download" else ""
_backup_busy = _row.get("kind") == "backup" and _row.get("status") in ("running", "queued")

if (
    _active
    and _purpose == "channel_download"
    and _row.get("status") == "succeeded"
    and st.session_state.get("channels_registered_job") != int(_active["id"])
):
    st.session_state["channels_registered_job"] = int(_active["id"])
    _register_download(_args)
    st.rerun()


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

if _ready := st.session_state.pop("channels_download_ready", None):
    st.success(f"✅ `{_ready}` baixado, indexado e selecionado na barra lateral.")
if _error := st.session_state.pop("channels_download_error", None):
    st.error(_error)

canais = channels.rows()
if not canais:
    st.info(
        "Nada em `backup/channels.txt` — use **📡 Listar canais agora** (abaixo) "
        "para descobrir os canais acessíveis."
    )
else:
    CH_PAGE_SIZE = 25

    def _clear_channel_query() -> None:
        # Roda antes do corpo do script (callback), quando ainda é seguro
        # escrever na chave do widget.
        st.session_state["ch_query"] = ""
        st.session_state.pop("pick_channel", None)
        flt.reset_page("ch")

    q1, q2 = st.columns([5, 1])
    with q1:
        st.text_input(
            "🔍 Buscar canal",
            key="ch_query",
            placeholder="título, @username ou ID",
            help="Filtra por título, @username ou ID — sem diferenciar maiúsculas.",
        )
    with q2:
        st.write("")
        st.button(
            "🧹 Limpar",
            key="ch_clear",
            on_click=_clear_channel_query,
            disabled=not (st.session_state.get("ch_query") or "").strip(),
        )

    query = (st.session_state.get("ch_query") or "").strip()
    if st.session_state.get("ch_sig") != query.lower():
        st.session_state["ch_sig"] = query.lower()
        st.session_state.pop("pick_channel", None)
        flt.reset_page("ch")

    filtrados = channels.filter_rows(canais, query)
    st.caption(
        f"**{len(filtrados)}** de **{len(canais)}** canal(is)"
        + (f' · filtro "{query}"' if query else "")
    )

    if not filtrados:
        st.info(f'Nenhum canal corresponde a "{query}".')
    else:
        page = flt.render_pagination(
            len(filtrados), flt.get_page("ch"), CH_PAGE_SIZE, prefix="ch"
        )
        inicio = (page - 1) * CH_PAGE_SIZE

        h1, h2, h3, h4, h5 = st.columns([2, 1, 2.5, 4, 3])
        h1.caption("**ID**")
        h2.caption("**Type**")
        h3.caption("**Username**")
        h4.caption("**Title**")
        h5.caption("**Download**")

        for row in filtrados[inicio : inicio + CH_PAGE_SIZE]:
            c1, c2, c3, c4, c5 = st.columns([2, 1, 2.5, 4, 3])
            with c1:
                st.caption(f"`{row['id']}`")
            with c2:
                st.caption(row["type"])
            with c3:
                st.caption(row["username"])
            with c4:
                st.markdown(f"**{row['title'] or '(sem título)'}**")
            with c5:
                if _downloading_id == str(row["id"]):
                    st.caption("⏳ baixando…")
                    continue
                baixado, fonte = channels.is_downloaded(row)
                if not baixado:
                    if st.button(
                        "⬇️ Baixar",
                        key=f"ch_dl_{row['id']}",
                        width="stretch",
                        disabled=_backup_busy,
                        help="Grava `CHANNEL`/`OUTPUT_DIR` no `.env` e baixa este canal "
                        "para `OUTPUT_BASE/<título>`.",
                    ):
                        _download(row)
                    continue
                if fonte is None:
                    # pasta com conteúdo que ainda não virou fonte (ex.: cópia manual)
                    with st.spinner(f"Registrando `{row['title'] or row['id']}`..."):
                        fonte = channels.ensure_source(row)
                        if fonte and not fonte.get("last_scanned_at"):
                            channels.scan(fonte)
                    if fonte:
                        st.rerun()
                    st.caption("⚠️ pasta sem `backup.db`/`messages.json` indexável.")
                    continue
                qparams = {"source": str(fonte["id"])}
                g, p = st.columns(2)
                with g:
                    ui.page_link("pages/gallery.py", "🖼️ Galeria", query_params=qparams)
                with p:
                    ui.page_link("pages/player.py", "▶️ Reprodutor", query_params=qparams)

        flt.render_pagination(
            len(filtrados), page, CH_PAGE_SIZE, prefix="ch", instance="bottom"
        )

        opcoes = {
            f"{row['title'] or '(sem título)'} · {row['username']} · {row['id']}": row["id"]
            for row in filtrados
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
