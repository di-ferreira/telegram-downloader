from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import REPO_ROOT, SCAN_ROOTS
from core import content, paths, registry

st.title("Fontes de conteúdo")

sources = registry.list_sources()

# ------------------------------------------------------- rescan solicitado
pending = st.session_state.pop("rescan_request", None)
if pending:
    st.info(f"Re-escanear solicitado para a fonte **#{pending}**.")


def _run_scan(source_id: int, verify_files: bool = True) -> None:
    source = registry.get_source(source_id)
    if not source:
        st.error("Fonte não encontrada.")
        return
    if not source.get("db_path") and not source.get("json_path"):
        detection = content.detect(Path(source["root_path"]))
        if not detection["db_path"] and not detection["json_path"]:
            st.error(
                "Nenhum `backup.db` ou `messages.json` encontrado nesta pasta. "
                "Rode o backup primeiro."
            )
            return
        registry.update_source(
            source_id,
            db_path=detection["db_path"],
            json_path=detection["json_path"],
            channel=detection.get("channel"),
        )

    with st.status(f"Indexando {source['name']}...", expanded=True) as status:
        progress = st.progress(0.0, text="Iniciando...")

        def _tick(message: str, current: int, total: int) -> None:
            progress.progress(0.5 if not total else min(current / total, 1.0), text=message)

        try:
            stats = content.scan_source(source_id, verify_files=verify_files, progress=_tick)
        except Exception as exc:  # pragma: no cover - surfaced to the user
            status.update(label=f"Falha no scan: {exc}", state="error")
            st.exception(exc)
            return
        progress.progress(1.0, text="Concluído")
        status.update(
            label=(
                f"{stats['message_count']:,} mensagens · {stats['media_count']:,} mídias · "
                f"{paths.human_size(stats['total_bytes'])} · "
                f"{stats['missing_files']:,} ausentes"
            ),
            state="complete",
        )


# ------------------------------------------------------------------ adicionar
st.subheader("Adicionar pasta de backup")
with st.form("add_source", clear_on_submit=True):
    col1, col2, col3 = st.columns([4, 3, 2])
    with col1:
        folder = st.text_input(
            "Caminho da pasta",
            value=str(REPO_ROOT / "downloads"),
            help="Pasta que contém `backup.db`, `messages.json` e `media/`.",
        )
    with col2:
        name = st.text_input("Nome da fonte (opcional)", placeholder="meu_canal")
    with col3:
        st.write("")  # vertical alignment
        submitted = st.form_submit_button("➕ Adicionar", type="primary")

if submitted:
    path = Path(folder).expanduser()
    if not path.is_dir():
        st.error(f"Pasta não existe: `{path}`")
    else:
        detection = content.detect(path)
        if not detection["db_path"] and not detection["json_path"]:
            st.error("A pasta não contém `backup.db` nem `messages.json`.")
        else:
            created = registry.add_source(
                path,
                name=name or path.name,
                channel=detection.get("channel"),
                db_path_=detection["db_path"],
                json_path=detection["json_path"],
            )
            if created:
                st.success(f"Fonte registrada: **{created['name']}**")
                _run_scan(int(created["id"]))
                st.rerun()

# ------------------------------------------------------------ procurar no projeto
with st.expander("🔎 Procurar backups neste projeto", expanded=not sources):
    if st.button("Varrer pastas do repositório", type="primary"):
        with st.status("Procurando backups..."):
            found = content.find_backup_folders(SCAN_ROOTS)
        if not found:
            st.warning("Nenhum backup encontrado. Rode `python backup/backup.py`.")
        else:
            added = 0
            for folder_path in found:
                detection = content.detect(folder_path)
                if registry.get_source_by_root(str(folder_path.resolve())):
                    continue
                registry.add_source(
                    folder_path,
                    name=folder_path.name,
                    channel=detection.get("channel"),
                    db_path_=detection["db_path"],
                    json_path=detection["json_path"],
                )
                added += 1
            st.success(f"{len(found)} pasta(s) encontrada(s), {added} nova(s) registrada(s).")
            for folder_path in found:
                source = registry.get_source_by_root(str(folder_path.resolve()))
                if source and not source.get("message_count"):
                    _run_scan(int(source["id"]))
            st.rerun()

# ------------------------------------------------------------------ listagem
st.subheader("Fontes cadastradas")
if not sources:
    st.info("Nenhuma fonte ainda.")
    st.stop()

for source in sources:
    source_id = int(source["id"])
    enabled = bool(source.get("enabled"))
    with st.container(border=True):
        c1, c2, c3, c4, c5, c6, c7 = st.columns([3, 3, 1.4, 1.4, 1.6, 1.6, 2])
        with c1:
            st.markdown(f"**{source['name']}** {'🟢' if enabled else '⏸️'}")
            st.caption(source.get("channel") or "canal desconhecido")
        with c2:
            st.caption(f"`{source.get('root_path')}`")
            st.caption(f"scan: {str(source.get('last_scanned_at') or '—')[:19]}")
        with c3:
            st.metric("Mensagens", f"{source.get('message_count') or 0:,}")
        with c4:
            st.metric("Mídias", f"{source.get('media_count') or 0:,}")
        with c5:
            st.metric("Tamanho", paths.human_size(source.get("total_bytes")))
        with c6:
            st.metric("Ausentes", f"{source.get('missing_files') or 0:,}")
        with c7:
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("🔄", key=f"scan_{source_id}", help="Re-escanear"):
                    _run_scan(source_id)
                    st.rerun()
            with a2:
                label = "⏸️" if enabled else "▶️"
                if st.button(label, key=f"toggle_{source_id}", help="Ativar/desativar"):
                    registry.set_enabled(source_id, not enabled)
                    st.rerun()
            with a3:
                if st.button("🗑️", key=f"del_{source_id}", help="Remover (não apaga arquivos)"):
                    st.session_state["confirm_delete"] = source_id

    confirm = st.session_state.get("confirm_delete")
    if confirm == source_id:
        st.warning(
            f"Remover **{source['name']}** do índice? Os arquivos em disco **não** serão apagados."
        )
        d1, d2 = st.columns([1, 1])
        with d1:
            if st.button("Confirmar remoção", key=f"confirm_del_{source_id}"):
                registry.delete_source(source_id)
                st.session_state.pop("confirm_delete", None)
                if st.session_state.get("source_id") == source_id:
                    st.session_state["source_id"] = None
                st.rerun()
        with d2:
            if st.button("Cancelar", key=f"cancel_del_{source_id}"):
                st.session_state.pop("confirm_delete", None)
                st.rerun()

if pending:
    _run_scan(int(pending))
    st.rerun()
