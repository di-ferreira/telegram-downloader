from __future__ import annotations

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from core import registry


def page_link(page: str, label: str, icon: str | None = None) -> None:
    """Navega para outra página, degradando para legenda fora da navegação.

    ``st.page_link`` só aceita páginas registradas em ``st.navigation``; num
    script ou teste que roda a página sozinha ele lança
    ``StreamlitPageNotFoundError``, então ali o link vira texto simples.
    """
    try:
        st.page_link(page, label=label, icon=icon)
    except StreamlitPageNotFoundError:
        st.caption(f"{(icon + ' ') if icon else ''}{label}")


def current_source() -> dict | None:
    return registry.get_source(st.session_state.get("source_id"))


def guard_source() -> dict | None:
    """Return the active source, or render an empty state and return ``None``."""
    source = current_source()
    if source:
        return source
    sources = registry.list_sources()
    if not sources:
        st.warning("Nenhuma fonte de conteúdo cadastrada ainda.")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Cadastrar fonte", type="primary"):
                st.switch_page("pages/sources.py")
        with col2:
            if st.button("Procurar backups no projeto"):
                st.switch_page("pages/sources.py")
    else:
        st.info("Selecione uma fonte na barra lateral.")
    st.stop()


def source_header(source: dict) -> None:
    status = f"último scan em {source.get('last_scanned_at') or '—'}"
    st.caption(
        f"📁 `{source.get('root_path')}` · {source.get('message_count', 0):,} mensagens · {status}".replace(",", ".")
    )


def no_results() -> None:
    st.info("Nenhum resultado com os filtros atuais.")
