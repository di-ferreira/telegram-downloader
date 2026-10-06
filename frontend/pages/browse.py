from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from components import cards, filters as flt, ui
from config import PAGE_SIZE
from core import exports, media_server, paths, queries, registry

source = ui.guard_source()
source_id = int(source["id"])

st.title("Mensagens")
ui.source_header(source)

# ------------------------------------------------------------------ filtros
with st.expander("🔎 Filtros", expanded=True):
    active = flt.render_filters(source, prefix="br")

signature = repr(active)
if st.session_state.get("br_signature") != signature:
    st.session_state["br_signature"] = signature
    st.session_state["br_page"] = 1

page = flt.get_page("br")
rows, total = queries.search(source, active, page=page, page_size=PAGE_SIZE)

toolbar = st.columns([2, 2, 3, 3])
with toolbar[0]:
    if st.button("🔄 Preparar exportação"):
        with st.status("Coletando resultados..."):
            all_rows, all_total = queries.fetch_all(source, active, max_rows=5000)
        st.session_state["export_csv"] = exports.rows_to_csv(all_rows)
        st.session_state["export_json"] = exports.rows_to_json(all_rows)
        st.session_state["export_count"] = len(all_rows)
        st.session_state["export_capped"] = all_total > len(all_rows)
with toolbar[1]:
    if st.button("⬇️ Exportar mídia (.zip)"):
        with st.status("Compactando arquivos..."):
            payload, included, skipped = exports.files_to_zip(source, rows)
        st.session_state["export_zip"] = payload
        st.session_state["export_zip_info"] = f"{included} arquivo(s), {skipped} pulado(s)"
with toolbar[2]:
    if st.session_state.get("export_csv"):
        st.download_button(
            f"CSV ({st.session_state.get('export_count', 0)})",
            data=st.session_state["export_csv"],
            file_name=f"mensagens_{source_id}.csv",
            mime="text/csv",
        )
with toolbar[3]:
    if st.session_state.get("export_json"):
        st.download_button(
            "JSON",
            data=st.session_state["export_json"],
            file_name=f"mensagens_{source_id}.json",
            mime="application/json",
        )

if st.session_state.get("export_zip"):
    c1, c2 = st.columns([4, 1])
    with c1:
        st.caption(f"ZIP pronto: {st.session_state.get('export_zip_info')}")
    with c2:
        st.download_button(
            "Baixar ZIP",
            data=st.session_state["export_zip"],
            file_name=f"midias_{source_id}.zip",
            mime="application/zip",
        )

if st.session_state.get("export_capped"):
    st.warning("Exportação limitada a 5.000 mensagens. Refine os filtros.")

# ------------------------------------------------------------------- tabela
if not rows:
    ui.no_results()
    st.stop()

table = pd.DataFrame(cards.table_rows(rows))
event = st.dataframe(
    table,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="br_table",
)

sel = getattr(event, "selection", event)
if isinstance(sel, dict):
    selected_rows = list(sel.get("rows") or [])
else:
    selected_rows = list(getattr(sel, "rows", None) or [])

flt.render_pagination(total, page, PAGE_SIZE, prefix="br")

# --------------------------------------------------------------- detalhamento
st.divider()
st.subheader("Detalhe")

selected: dict | None = None
if selected_rows and selected_rows[0] < len(rows):
    selected = rows[selected_rows[0]]

manual_id = st.text_input("Ou abra pelo ID da mensagem", key="br_manual_id")
if manual_id:
    try:
        candidate = queries.get_message(source, int(manual_id))
        if candidate:
            selected = candidate
        else:
            st.warning(f"Mensagem {manual_id} não encontrada com os filtros atuais.")
    except ValueError:
        st.warning("Informe um número de ID.")

if selected is None:
    st.info("Selecione uma linha da tabela para ver o conteúdo completo.")
    st.stop()

message_id = int(selected.get("id") or 0)
media_key = selected.get("media_key")
url = media_server.media_url(source_id, media_key)
kind = cards.kind_of(selected)

head = st.columns([3, 2, 2, 2, 2])
with head[0]:
    st.markdown(f"### Mensagem `{message_id}`")
    st.caption(f"{str(selected.get('date') or '')[:19]} · {selected.get('sender_name') or '—'}")
with head[1]:
    st.metric("Views", selected.get("views") or "—")
with head[2]:
    st.metric("Tipo", selected.get("media_type") or "texto")
with head[3]:
    st.metric("Tamanho", paths.human_size(selected.get("file_size")))
with head[4]:
    st.metric("Progresso", flt.status_badge(selected.get("progress_status")))

if selected.get("text"):
    st.markdown("---")
    st.markdown(selected["text"])

if url and kind in ("video", "audio", "image"):
    st.markdown("---")
    if kind == "image":
        st.image(url, width="stretch", caption=selected.get("file_name"))
    else:
        resume = 0.0
        if selected.get("progress_status") == "in_progress":
            resume = float(selected.get("progress_position") or 0)
        media_render = st.columns([4, 1])
        with media_render[0]:
            if kind == "video":
                st.video(url, start_time=int(resume))
            else:
                st.audio(url, start_time=int(resume))
        with media_render[1]:
            st.caption("Para rastrear o progresso, use a página **Reprodutor**.")
            if st.button("▶️ Abrir no reprodutor"):
                st.session_state["detail_message_id"] = message_id
                st.switch_page("pages/player.py")

st.markdown("---")
actions = st.columns(6)
with actions[0]:
    if st.button("▶️ Reproduzir", disabled=not media_key):
        st.session_state["detail_message_id"] = message_id
        st.switch_page("pages/player.py")
with actions[1]:
    if st.button("⭐ Favoritar" if not selected.get("is_favorite") else "☆ Remover favorito"):
        registry.toggle_favorite(source_id, message_id)
        st.rerun()
with actions[2]:
    if st.button("✅ Assistido", disabled=not media_key):
        registry.upsert_media_state(
            source_id,
            media_key,
            message_id=message_id,
            status="watched",
            percent=1.0,
        )
        st.rerun()
with actions[3]:
    if st.button("↩️ Zerar progresso", disabled=not media_key):
        registry.upsert_media_state(
            source_id,
            media_key,
            message_id=message_id,
            status="new",
            percent=0.0,
            position_sec=0.0,
        )
        st.rerun()
with actions[4]:
    if url:
        st.markdown(f"[⬇️ Arquivo]({url})")
with actions[5]:
    resolved = paths.resolve_media(Path(source["root_path"]), media_key)
    if resolved:
        st.code(str(resolved), language=None)
    else:
        st.caption("arquivo não encontrado")

note = st.text_area(
    "Anotação",
    value=(selected.get("progress_note") or ""),
    key=f"note_{message_id}",
)
if st.button("💾 Salvar anotação", disabled=not media_key):
    registry.upsert_media_state(
        source_id,
        media_key,
        message_id=message_id,
        note=note,
    )
    st.success("Anotação salva.")
