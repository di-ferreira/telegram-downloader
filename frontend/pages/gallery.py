from __future__ import annotations

import streamlit as st

from components import cards, filters as flt, ui
from core import queries

GL_PAGE_SIZE = 24

source = ui.guard_source()
source_id = int(source["id"])

st.title("Galeria")
ui.source_header(source)

with st.expander("🔎 Filtros", expanded=True):
    active = flt.render_filters(source, prefix="gl", with_status=True, with_order=False)

active.only = "media"
st.caption("A galeria lista apenas mensagens com mídia.")

signature = repr(active)
if st.session_state.get("gl_signature") != signature:
    st.session_state["gl_signature"] = signature
    st.session_state["gl_page"] = 1

page = flt.get_page("gl")
rows, total = queries.search(source, active, page=page, page_size=GL_PAGE_SIZE)

if not rows:
    ui.no_results()
    st.stop()

flt.render_pagination(total, page, GL_PAGE_SIZE, prefix="gl", instance="top")
cards.render_grid(source, rows, columns=4, key_prefix=f"g{page}_")
flt.render_pagination(total, page, GL_PAGE_SIZE, prefix="gl", instance="bottom")

st.caption(f"{total} arquivo(s) com os filtros atuais.")
