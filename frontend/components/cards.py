from __future__ import annotations

from typing import Any

import streamlit as st

from core import media_server, paths


def media_icon(media_type: str | None, mime: str | None = None) -> str:
    mime = mime or ""
    if (media_type or "") == "photo" or mime.startswith("image"):
        return "🖼️"
    if (media_type or "") == "video" or mime.startswith("video"):
        return "🎬"
    if (media_type or "") == "audio" or mime.startswith("audio"):
        return "🎵"
    if (media_type or "") == "gif":
        return "🎞️"
    if (media_type or "") == "sticker":
        return "🙂"
    if (media_type or "") == "document":
        return "📄"
    return "💬"


def kind_of(row: dict) -> str:
    mime = row.get("mime_type") or ""
    media_type = row.get("media_type") or ""
    if media_type == "audio" or mime.startswith("audio"):
        return "audio"
    if media_type == "video" or mime.startswith("video") or media_type == "gif":
        return "video"
    if media_type == "photo" or mime.startswith("image") or media_type in ("sticker", "gif"):
        return "image"
    if not row.get("media_path"):
        return "text"
    return "document"


def is_image(row: dict) -> bool:
    mime = row.get("mime_type") or ""
    media_type = row.get("media_type") or ""
    return media_type == "photo" or mime.startswith("image/") or media_type == "sticker"


def progress_line(row: dict) -> str:
    status = row.get("progress_status")
    percent = float(row.get("progress_percent") or 0)
    if status == "watched":
        return "✅ Assistido"
    if status == "in_progress" and percent:
        return f"▶️ {percent * 100:.0f}% assistido"
    if status:
        return "⬜ Não assistido"
    return ""


def render_card(source: dict, row: dict, *, key_prefix: str = "card") -> dict:
    """One gallery tile: thumbnail when possible, metadata otherwise."""
    source_id = int(source["id"])
    media_key = row.get("media_key")
    url = media_server.media_url(source_id, media_key)
    label = row.get("file_name") or paths.to_posix(media_key or "") or f"msg {row.get('id')}"

    with st.container():
        if url and is_image(row):
            st.image(url, width="stretch", alt=str(label))
        else:
            st.markdown(f"# {media_icon(row.get('media_type'), row.get('mime_type'))}")
            st.caption(str(label)[:80])

        st.caption(
            f"#{row.get('id')} · {str(row.get('date') or '')[:10]} · "
            f"{paths.human_size(row.get('file_size'))}"
        )
        line = progress_line(row)
        if line:
            st.caption(line)
        if row.get("text"):
            text = str(row["text"]).replace("\n", " ")
            st.caption(text[:120] + ("…" if len(text) > 120 else ""))

        if st.button(
            "Abrir",
            key=f"{key_prefix}_{row.get('id')}",
            use_container_width=True,
        ):
            st.session_state["detail_message_id"] = int(row.get("id"))
            st.session_state["gallery_page_context"] = True
            st.switch_page("pages/player.py")
    return row


def render_grid(source: dict, rows: list[dict], columns: int = 4, key_prefix: str = "card") -> None:
    if not rows:
        st.info("Nenhum arquivo encontrado com os filtros atuais.")
        return
    cols = None
    for index, row in enumerate(rows):
        if cols is None or index % columns == 0:
            cols = st.columns(columns)
        with cols[index % columns]:
            render_card(source, row, key_prefix=f"{key_prefix}{index}")


def message_summary(row: dict) -> str:
    text = (row.get("text") or "").strip().replace("\n", " ")
    if text:
        return text[:200] + ("…" if len(text) > 200 else "")
    name = row.get("file_name") or row.get("media_type") or "mídia"
    return f"{media_icon(row.get('media_type'), row.get('mime_type'))} {name}"


def table_rows(rows: list[dict]) -> list[dict[str, Any]]:
    """Project message rows into the flat shape ``st.dataframe`` renders best."""
    out = []
    for row in rows:
        out.append(
            {
                "id": row.get("id"),
                "data": str(row.get("date") or "")[:19],
                "remetente": row.get("sender_name"),
                "tipo": row.get("media_type") or "texto",
                "arquivo": row.get("file_name"),
                "tamanho": paths.human_size(row.get("file_size")),
                "views": row.get("views"),
                "progresso": progress_line(row) or "-",
                "⭐": "★" if row.get("is_favorite") else "",
                "texto": (row.get("text") or "").replace("\n", " ")[:120],
            }
        )
    return out
