from __future__ import annotations

from pathlib import Path

import streamlit as st

from components import filters as flt, player as player_ui, ui
from core import media_server, paths, queries, registry

source = ui.guard_source()
source_id = int(source["id"])

st.title("Reprodutor")
ui.source_header(source)

# --------------------------------------------------------------------- fila
with st.expander("🎯 Fila de reprodução", expanded=True):
    queue_filters = flt.render_filters(
        source, prefix="pl", with_status=True, with_order=False
    )
    queue_filters.only = "media"
    refresh = st.button("🔄 Recarregar fila")

signature = repr(queue_filters)
if refresh or st.session_state.get("pl_signature") != signature:
    with st.status("Montando fila..."):
        rows, _total = queries.fetch_all(source, queue_filters, max_rows=200)
    st.session_state["pl_signature"] = signature
    st.session_state["pl_queue"] = [int(r["id"]) for r in rows]
    st.session_state["pl_rows"] = rows
    st.session_state["pl_index"] = 0

queue: list[dict] = list(st.session_state.get("pl_rows") or [])
queue_ids: list[int] = [int(r["id"]) for r in queue]

# A just-opened message always wins over the stored index.
detail_id = st.session_state.pop("detail_message_id", None)
if detail_id is not None:
    detail_id = int(detail_id)
    if detail_id in queue_ids:
        st.session_state["pl_index"] = queue_ids.index(detail_id)
    else:
        row = queries.get_message(source, detail_id)
        if row:
            st.session_state["pl_queue"] = [detail_id]
            st.session_state["pl_rows"] = [row]
            st.session_state["pl_index"] = 0

queue = list(st.session_state.get("pl_rows") or [])
queue_ids = [int(r["id"]) for r in queue]
if not queue:
    st.warning("Fila vazia. Ajuste os filtros ou selecione uma mensagem em **Mensagens**.")
    if st.button("Ir para Mensagens"):
        st.switch_page("pages/browse.py")
    st.stop()

index = int(st.session_state.get("pl_index", 0))
index = min(max(index, 0), len(queue) - 1)
st.session_state["pl_index"] = index
current = queue[index]

# ------------------------------------------------------------------ comandos
nav = st.columns([2, 3, 2, 3, 3])
with nav[0]:
    if st.button("⏮️ Anterior", disabled=index <= 0):
        st.session_state["pl_index"] = index - 1
        st.rerun()
with nav[1]:
    st.caption(f"**{index + 1} / {len(queue)}**")
with nav[2]:
    if st.button("Próximo ➡️", disabled=index >= len(queue) - 1):
        st.session_state["pl_index"] = index + 1
        st.rerun()
with nav[3]:
    if st.button("🔀 Embaralhar"):
        import random

        random.shuffle(queue)
        st.session_state["pl_rows"] = queue
        st.session_state["pl_queue"] = [int(r["id"]) for r in queue]
        st.session_state["pl_index"] = 0
        st.rerun()
with nav[4]:
    if st.button("🗂️ Ver na tabela"):
        st.session_state["br_manual_id"] = str(current.get("id"))
        st.switch_page("pages/browse.py")

# ---------------------------------------------------------------- conteúdo
message_id = int(current.get("id") or 0)
media_key = current.get("media_key")
mime = current.get("mime_type") or ""
media_type = current.get("media_type") or ""
if mime.startswith("audio") or media_type == "audio":
    kind = "audio"
elif mime.startswith("image") or media_type in ("photo", "sticker"):
    kind = "image"
else:
    kind = "video"

st.markdown(f"### {current.get('file_name') or f'Mensagem {message_id}'}")
st.caption(
    f"#{message_id} · {str(current.get('date') or '')[:19]} · "
    f"{current.get('sender_name') or '—'} · {paths.human_size(current.get('file_size'))}"
)
if current.get("text"):
    st.markdown(current["text"])

url = media_server.media_url(source_id, media_key)
if not url or not current.get("media_exists"):
    st.error("Arquivo de mídia ausente ou ilegível nesta fonte.")
    resolved = paths.resolve_media(Path(source["root_path"]), media_key)
    if resolved:
        st.code(str(resolved), language=None)
    st.stop()

if kind == "image":
    st.image(url, width="stretch")
    if st.button("✅ Marcar como assistido"):
        player_ui.set_status(source_id, media_key, "watched", message_id)
        if index < len(queue) - 1:
            st.session_state["pl_index"] = index + 1
        st.rerun()
else:
    resume = player_ui.resume_position(source_id, media_key, message_id)
    state = player_ui.render_player(
        source_id=source_id,
        media_key=media_key,
        url=url,
        message_id=message_id,
        kind=kind,
        start_at=resume,
    )
    if state:
        percent = float(state.get("percent") or 0)
        st.progress(min(percent, 1.0), text=f"{percent * 100:.0f}% · {kind}")
        if state.get("error"):
            st.error("O navegador não conseguiu reproduzir este arquivo.")
    else:
        st.caption("O progresso é salvo automaticamente durante a reprodução.")

# ------------------------------------------------------------------ ações
actions = st.columns(6)
row_state = registry.get_media_state_by_message(source_id, message_id)
with actions[0]:
    if st.button("✅ Assistido"):
        player_ui.set_status(source_id, media_key, "watched", message_id)
        st.rerun()
with actions[1]:
    if st.button("↩️ Reiniciar"):
        player_ui.set_status(source_id, media_key, "new", message_id)
        st.rerun()
with actions[2]:
    is_fav = registry.is_favorite(source_id, message_id)
    if st.button("⭐ Favoritar" if not is_fav else "☆ Remover favorito"):
        registry.toggle_favorite(source_id, message_id)
        st.rerun()
with actions[3]:
    st.metric("Assistido", flt.status_badge((row_state or {}).get("status")))
with actions[4]:
    st.metric("Reproduções", (row_state or {}).get("play_count") or 0)
with actions[5]:
    if url:
        st.markdown(f"[⬇️ Arquivo]({url})")

note = st.text_area(
    "Anotação",
    value=(row_state or {}).get("note") or "",
    key=f"pl_note_{message_id}",
)
if st.button("💾 Salvar anotação"):
    registry.upsert_media_state(
        source_id, media_key, message_id=message_id, note=note
    )
    st.success("Anotação salva.")
