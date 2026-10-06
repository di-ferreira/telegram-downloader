from __future__ import annotations

from datetime import date

import streamlit as st

from config import MEDIA_TYPES
from core import queries
from core.queries import Filters

STATUS_LABELS = {
    "": "Sem registro",
    "new": "Não assistido",
    "in_progress": "Em progresso",
    "watched": "Assistido",
    "skipped": "Ignorado",
}


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def render_filters(
    source: dict,
    *,
    prefix: str = "flt",
    with_status: bool = True,
    with_order: bool = True,
) -> Filters:
    """Render filter widgets and return the resulting :class:`Filters`."""
    min_date, max_date = queries.date_bounds(source)
    min_d, max_d = _to_date(min_date), _to_date(max_date)
    senders = queries.distinct_senders(source)

    q = st.text_input(
        "Buscar texto",
        key=f"{prefix}_q",
        placeholder="palavra, frase ou ID da mensagem",
        help="Busca full-text (FTS5) sobre o conteúdo do canal.",
    )

    only = st.radio(
        "Conteúdo",
        ["Tudo", "Com mídia", "Só texto"],
        horizontal=True,
        key=f"{prefix}_only",
    )

    c1, c2 = st.columns(2)
    d1 = d2 = None
    if min_d or max_d:
        with c1:
            d1 = st.date_input(
                "De",
                value=min_d,
                min_value=min_d,
                max_value=max_d or min_d,
                key=f"{prefix}_d1",
            )
        with c2:
            d2 = st.date_input(
                "Até",
                value=max_d,
                min_value=min_d,
                max_value=max_d or min_d,
                key=f"{prefix}_d2",
            )

    types = st.multiselect(
        "Tipo de mídia",
        list(MEDIA_TYPES),
        key=f"{prefix}_types",
    )

    sender = st.selectbox(
        "Remetente",
        ["(todos)"] + senders,
        key=f"{prefix}_sender",
    )

    status = None
    if with_status:
        status = st.selectbox(
            "Progresso",
            ["(qualquer)", *STATUS_LABELS.keys()],
            format_func=lambda v: STATUS_LABELS.get(v, v),
            key=f"{prefix}_status",
        )

    fav_only = st.checkbox("Somente favoritos", key=f"{prefix}_fav")

    order = "desc"
    if with_order:
        order = st.radio(
            "Ordenação",
            ["Mais recentes", "Mais antigos"],
            horizontal=True,
            key=f"{prefix}_order",
        )
        order = "asc" if order == "Mais antigos" else "desc"

    # A date equal to the stored bound means "no restriction": that keeps
    # messages with an empty date visible.
    date_from = d1.isoformat() if (d1 and d1 != min_d) else None
    date_to = d2.isoformat() if (d2 and d2 != max_d) else None

    return Filters(
        q=q or "",
        date_from=date_from,
        date_to=date_to,
        media_types=tuple(types),
        sender=None if sender in (None, "(todos)") else sender,
        only={"Tudo": "all", "Com mídia": "media", "Só texto": "text"}[only],
        status=status if status not in (None, "(qualquer)") else None,
        favorites_only=bool(fav_only),
        order=order,
    )


def render_pagination(
    total: int,
    page: int,
    page_size: int,
    prefix: str = "pg",
    instance: str = "",
) -> int:
    """Page controls. ``prefix`` is the page-state key; ``instance`` only makes
    widget keys unique when the same control is rendered twice on a page."""
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), pages)
    left, mid, right = st.columns([1, 2, 1])
    with left:
        if st.button(
            "← Anterior",
            disabled=page <= 1,
            key=f"{prefix}_prev_{instance}" if instance else f"{prefix}_prev",
        ):
            st.session_state[f"{prefix}_page"] = page - 1
            st.rerun()
    with mid:
        st.caption(f"Página **{page}** de **{pages}** — {total} resultado(s)")
    with right:
        if st.button(
            "Próxima →",
            disabled=page >= pages,
            key=f"{prefix}_next_{instance}" if instance else f"{prefix}_next",
        ):
            st.session_state[f"{prefix}_page"] = page + 1
            st.rerun()
    return page


def get_page(prefix: str = "pg") -> int:
    return int(st.session_state.get(f"{prefix}_page", 1))


def reset_page(prefix: str = "pg") -> None:
    st.session_state[f"{prefix}_page"] = 1


def status_badge(status: str | None) -> str:
    return {
        "watched": "✅ Assistido",
        "in_progress": "▶️ Em progresso",
        "new": "⬜ Não assistido",
        "skipped": "⏭️ Ignorado",
    }.get(status or "", "⬜ Não assistido")
