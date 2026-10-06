from __future__ import annotations

import streamlit as st

from config import WATCHED_AT
from core import registry

_HTML = """
<div class="mp-wrap">
  <p class="mp-hint">Carregando reprodutor&hellip;</p>
</div>
"""

_CSS = """
.mp-wrap { width: 100%; }
.mp-wrap video, .mp-wrap audio {
  width: 100%;
  max-height: 70vh;
  background: #000;
  border-radius: 8px;
  outline: none;
}
.mp-wrap audio { height: 44px; background: transparent; }
.mp-hint { margin: 0; opacity: 0.65; font-size: 0.85rem; }
"""

_JS = """
export default function (component) {
  const { data, setStateValue, parentElement } = component;
  if (!data || !data.src) return;

  let el = parentElement.querySelector('.mp-player');
  if (!el) {
    const hint = parentElement.querySelector('.mp-hint');
    if (hint) hint.remove();
    el = document.createElement(data.kind === 'audio' ? 'audio' : 'video');
    el.className = 'mp-player';
    el.setAttribute('controls', '');
    el.setAttribute('playsinline', '');
    el.preload = 'metadata';
    parentElement.appendChild(el);
    bind(el, setStateValue);
  }

  if (el.dataset.src !== data.src) {
    el.dataset.src = data.src;
    el.dataset.startAt = String(data.start_at || 0);
    el.src = data.src;
  } else if (data.start_at != null && data.start_at !== undefined) {
    el.dataset.startAt = String(data.start_at);
  }

  function bind(node, push) {
    let lastSent = 0;
    let started = false;

    const send = (force) => {
      const duration = node.duration;
      if (!isFinite(duration) || duration <= 0) return;
      const current = node.currentTime || 0;
      const percent = Math.min(Math.max(current / duration, 0), 1);
      const now = Date.now();
      if (!force && now - lastSent < 2000) return;
      lastSent = now;
      push('progress', {
        current: Math.round(current * 100) / 100,
        duration: Math.round(duration * 100) / 100,
        percent: Math.round(percent * 1000) / 1000,
        paused: !!node.paused,
        ended: !!node.ended,
        started: started,
      });
    };

    node.addEventListener('loadedmetadata', () => {
      const target = parseFloat(node.dataset.startAt || '0');
      if (target > 0.5 && isFinite(node.duration) && Math.abs(node.currentTime - target) > 0.5) {
        try { node.currentTime = Math.min(target, Math.max(node.duration - 0.25, 0)); } catch (e) {}
      }
      send(true);
    });
    node.addEventListener('timeupdate', () => { started = true; send(false); });
    node.addEventListener('pause', () => send(true));
    node.addEventListener('seeked', () => send(true));
    node.addEventListener('ended', () => send(true));
    node.addEventListener('error', () => {
      push('progress', { current: 0, duration: 0, percent: 0, paused: true, ended: false, started: false, error: true });
    });
  }
}
"""

_component = st.components.v2.component(
    "tg_media_player",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def _classify(kind: str | None, mime: str | None, media_type: str | None) -> str:
    if kind:
        return kind
    if (media_type or "") == "audio" or (mime or "").startswith("audio"):
        return "audio"
    if (media_type or "") in ("gif", "photo", "sticker") and (mime or "").startswith("image"):
        return "image"
    if (mime or "").startswith("video") or (media_type or "") in ("video", "gif"):
        return "video"
    if (mime or "").startswith("image"):
        return "image"
    return "document"


def _persist(
    source_id: int,
    media_key: str,
    message_id: int | None,
    kind: str,
    state: dict,
) -> None:
    if not state or not isinstance(state, dict):
        return
    percent = float(state.get("percent") or 0.0)
    duration = float(state.get("duration") or 0.0)
    current = float(state.get("current") or 0.0)
    ended = bool(state.get("ended"))
    touched = percent >= 0.01 or bool(state.get("started")) or ended

    if ended or percent >= WATCHED_AT:
        status = "watched"
    elif touched:
        status = "in_progress"
    else:
        return

    existing = None
    if message_id is not None:
        existing = registry.get_media_state_by_message(source_id, message_id)
    if existing is None and media_key:
        existing = registry.get_media_state(source_id, media_key)

    play_count = int(existing.get("play_count") or 0) if existing else 0
    if not existing or existing.get("status") == "new":
        play_count += 1

    registry.upsert_media_state(
        source_id,
        media_key,
        message_id=message_id,
        status=status,
        position_sec=round(current, 2),
        duration_sec=round(duration, 2),
        percent=round(percent, 4),
        play_count=play_count,
        last_played_at=registry.now_iso(),
        kind=kind,
    )


def render_player(
    *,
    source_id: int,
    media_key: str,
    url: str,
    message_id: int | None = None,
    kind: str = "video",
    start_at: float = 0.0,
) -> dict | None:
    """Mount the player component and persist playback state on every report."""
    session_key = f"tg_player_{source_id}_{media_key}"

    def _on_change() -> None:
        state = st.session_state.get(session_key)
        if isinstance(state, dict):
            try:
                _persist(source_id, media_key, message_id, kind, state)
            except Exception:
                pass

    result = _component(
        data={"src": url, "kind": kind, "start_at": float(start_at or 0.0)},
        key=session_key,
        on_progress_change=_on_change,
        width="stretch",
        height="content",
    )
    state = st.session_state.get(session_key)
    if isinstance(state, dict):
        return state
    return dict(result.progress) if getattr(result, "progress", None) else None


def resume_position(source_id: int, media_key: str, message_id: int | None) -> float:
    row = None
    if message_id is not None:
        row = registry.get_media_state_by_message(source_id, message_id)
    if row is None:
        row = registry.get_media_state(source_id, media_key)
    if not row:
        return 0.0
    if row.get("status") == "watched":
        return 0.0
    return float(row.get("position_sec") or 0.0)


def set_status(source_id: int, media_key: str, status: str, message_id: int | None = None) -> None:
    percent = 1.0 if status == "watched" else 0.0
    registry.upsert_media_state(
        source_id,
        media_key,
        message_id=message_id,
        status=status,
        percent=percent,
        position_sec=0.0 if status in ("watched", "new") else None,
    )
