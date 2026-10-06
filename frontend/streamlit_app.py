from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Telegram Downloader",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core import job_runner, media_server, registry  # noqa: E402

registry.init()
job_runner.reset_interrupted_jobs()


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 📥 Telegram Downloader")
        sources = [s for s in registry.list_sources() if s.get("enabled")]
        if not sources:
            st.warning("Nenhuma fonte cadastrada.")
            if st.button("➕ Cadastrar fonte", use_container_width=True):
                st.switch_page("pages/sources.py")
            active = None
        else:
            labels = {
                f"{s['name']} — {s.get('message_count', 0)} msgs": s["id"] for s in sources
            }
            previous = st.session_state.get("source_id")
            index = 0
            for label, sid in labels.items():
                if sid == previous:
                    index = list(labels).index(label)
            selected = st.selectbox("Fonte de conteúdo", list(labels), index=index)
            active = labels[selected]

        st.session_state["source_id"] = active

        st.divider()
        try:
            status = media_server.server_status()
            st.caption(
                f"Servidor de mídia: {'🟢' if status['running'] else '🔴'} "
                f"`{status['url'] or '—'}`"
            )
        except Exception:
            st.caption("Servidor de mídia: indisponível")
        st.caption("Acesso somente local (127.0.0.1).")

        if st.button("🔄 Re-escanear fonte", use_container_width=True, disabled=not active):
            st.session_state["rescan_request"] = active
            st.switch_page("pages/sources.py")


_render_sidebar()

_navigation = st.navigation(
    {
        "Biblioteca": [
            st.Page("pages/home.py", title="Dashboard", icon="🏠", default=True),
            st.Page("pages/browse.py", title="Mensagens", icon="💬"),
            st.Page("pages/gallery.py", title="Galeria", icon="🖼️"),
            st.Page("pages/player.py", title="Reprodutor", icon="▶️"),
        ],
        "Dados": [
            st.Page("pages/sources.py", title="Fontes", icon="🗂️"),
            st.Page("pages/jobs.py", title="Backup & Restore", icon="⚙️"),
        ],
    },
    position="sidebar",
    expanded=True,
)
_navigation.run()
