from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from config import LIBRARY_DB, MEDIA_TYPES, PROGRESS_STATUSES
from core import content, paths, registry

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass
class Filters:
    q: str = ""
    date_from: str | None = None
    date_to: str | None = None
    media_types: tuple[str, ...] = ()
    sender: str | None = None
    only: str = "all"  # all | media | text
    status: str | None = None  # None = any, "" = sem registro
    favorites_only: bool = False
    order: str = "desc"

    def is_empty(self) -> bool:
        return (
            not self.q
            and not self.date_from
            and not self.date_to
            and not self.media_types
            and not self.sender
            and self.only == "all"
            and not self.status
            and not self.favorites_only
        )


@contextmanager
def _hybrid(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Registry (read-only usage) + backup database attached read-only."""
    uri = "file:" + Path(LIBRARY_DB).as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute(
            "ATTACH DATABASE ? AS src",
            ("file:" + Path(db_path).as_posix() + "?mode=ro",),
        )
        yield conn
    finally:
        conn.close()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fts_query(q: str) -> str | None:
    tokens = _TOKEN_RE.findall(q or "")
    if not tokens:
        return None
    return " AND ".join(f"{t}*" for t in tokens[:12])


def _conditions(source_id: int, f: Filters, use_fts: bool) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    q = (f.q or "").strip()
    if q:
        if use_fts:
            match = _fts_query(q)
            if match:
                clauses.append(
                    "m.id IN (SELECT message_id FROM fts_msg WHERE fts_msg MATCH ? AND source_id = ?)"
                )
                params.extend([match, source_id])
            else:
                use_fts = False
        if not use_fts:
            like = f"%{_escape_like(q)}%"
            clauses.append(
                "(m.text LIKE ? ESCAPE '\\' OR m.sender_name LIKE ? ESCAPE '\\' OR CAST(m.id AS TEXT) = ?)"
            )
            params.extend([like, like, q])

    if f.date_from:
        clauses.append("substr(m.date, 1, 10) >= ?")
        params.append(f.date_from)
    if f.date_to:
        clauses.append("substr(m.date, 1, 10) <= ?")
        params.append(f.date_to)

    if f.media_types:
        marks = ", ".join("?" for _ in f.media_types)
        clauses.append(f"m.media_type IN ({marks})")
        params.extend(f.media_types)

    if f.sender:
        clauses.append("m.sender_name = ?")
        params.append(f.sender)

    if f.only == "media":
        clauses.append("m.media_path IS NOT NULL")
    elif f.only == "text":
        clauses.append("(m.media_path IS NULL OR m.media_path = '')")

    if f.status == "":
        clauses.append("ms.media_key IS NULL")
    elif f.status:
        clauses.append("ms.status = ?")
        params.append(f.status)

    if f.favorites_only:
        clauses.append("fav.message_id IS NOT NULL")

    # source_id is bound by the JOIN clauses, never by WHERE: a NULL side of a
    # LEFT JOIN must keep the row visible.
    return clauses, params


_SELECT = """
SELECT m.id, m.date, m.text, m.sender_id, m.sender_name, m.message_type, m.views,
       m.media_path, m.media_type, m.file_name, m.file_size, m.mime_type, m.md5_hash,
       ms.media_key AS state_key, ms.status AS progress_status,
       ms.percent AS progress_percent, ms.position_sec AS progress_position,
       ms.duration_sec AS progress_duration, ms.note AS progress_note,
       CASE WHEN fav.message_id IS NULL THEN 0 ELSE 1 END AS is_favorite
FROM src.messages m
LEFT JOIN media_state ms ON ms.source_id = ? AND ms.message_id = m.id
LEFT JOIN favorites fav ON fav.source_id = ? AND fav.message_id = m.id
"""


def search(
    source: dict,
    filters: Filters,
    page: int = 1,
    page_size: int = 50,
    count_only: bool = False,
) -> tuple[list[dict], int]:
    """Return ``(rows, total)`` for one page of messages."""
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        return _search_json(source, filters, page, page_size, count_only)

    source_id = int(source["id"])
    use_fts = bool(filters.q) and registry.fts_available(source_id)
    clauses, extra = _conditions(source_id, filters, use_fts)
    where = " AND ".join(clauses) if clauses else "1 = 1"

    try:
        with _hybrid(source["db_path"]) as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM src.messages m "
                    f"LEFT JOIN media_state ms ON ms.source_id = ? AND ms.message_id = m.id "
                    f"LEFT JOIN favorites fav ON fav.source_id = ? AND fav.message_id = m.id "
                    f"WHERE {where}",
                    (source_id, source_id, *extra),
                ).fetchone()[0]
            )
            if count_only:
                return [], total

            order = "m.id ASC" if filters.order == "asc" else "m.id DESC"
            offset = max(page - 1, 0) * page_size
            rows = conn.execute(
                f"{_SELECT} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                (source_id, source_id, *extra, page_size, offset),
            ).fetchall()
    except sqlite3.Error:
        # Content database busy/corrupt - degrade instead of crashing the page.
        return _search_json(source, filters, page, page_size, count_only)

    return [_decorate(dict(r), source) for r in rows], total


def _search_json(
    source: dict,
    filters: Filters,
    page: int,
    page_size: int,
    count_only: bool,
) -> tuple[list[dict], int]:
    if not source.get("json_path") or not Path(source["json_path"]).exists():
        return [], 0

    source_id = int(source["id"])
    states = _states_by_message(source_id)
    favorites = _favorites(source_id)
    q = (filters.q or "").strip().lower()

    matched: list[dict] = []
    for msg in content.load_json(source["json_path"]):
        text = (msg.get("text") or "")
        media_path = msg.get("media_path")
        if q and q not in text.lower() and q not in str(msg.get("sender_name") or "").lower() \
                and str(msg.get("id")) != q:
            continue
        date = str(msg.get("date") or "")[:10]
        if filters.date_from and date < filters.date_from:
            continue
        if filters.date_to and date > filters.date_to:
            continue
        if filters.media_types and msg.get("media_type") not in filters.media_types:
            continue
        if filters.sender and msg.get("sender_name") != filters.sender:
            continue
        if filters.only == "media" and not media_path:
            continue
        if filters.only == "text" and media_path:
            continue
        state = states.get(int(msg.get("id") or 0))
        if filters.status == "" and state is not None:
            continue
        if filters.status and (state is None or state.get("status") != filters.status):
            continue
        if filters.favorites_only and int(msg.get("id") or 0) not in favorites:
            continue
        row = dict(msg)
        row["is_favorite"] = 1 if int(msg.get("id") or 0) in favorites else 0
        row.update(
            state_key=(state or {}).get("media_key"),
            progress_status=(state or {}).get("status"),
            progress_percent=(state or {}).get("percent"),
            progress_position=(state or {}).get("position_sec"),
            progress_duration=(state or {}).get("duration_sec"),
            progress_note=(state or {}).get("note"),
        )
        matched.append(row)

    matched.sort(key=lambda r: int(r.get("id") or 0), reverse=filters.order != "asc")
    total = len(matched)
    if count_only:
        return [], total
    offset = max(page - 1, 0) * page_size
    page_rows = matched[offset : offset + page_size]
    return [_decorate(r, source) for r in page_rows], total


def _decorate(row: dict, source: dict) -> dict:
    key = row.get("state_key")
    if not key:
        key = paths.media_key(Path(source["root_path"]), row.get("media_path"))
    row["media_key"] = key
    row["media_exists"] = bool(paths.resolve_media(Path(source["root_path"]), key)) if key else False
    return row


def _states_by_message(source_id: int) -> dict[int, dict]:
    with registry.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM media_state WHERE source_id = ? AND message_id IS NOT NULL",
            (source_id,),
        ).fetchall()
    return {int(r["message_id"]): dict(r) for r in rows}


def _favorites(source_id: int) -> set[int]:
    with registry.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT message_id FROM favorites WHERE source_id = ?", (source_id,)
        ).fetchall()
    return {int(r[0]) for r in rows}


def get_messages_by_ids(source: dict, ids: list[int]) -> list[dict]:
    """Fetch specific messages without relying on the text search index."""
    ids = [int(i) for i in ids if i is not None]
    if not ids or not source.get("db_path") or not Path(source["db_path"]).exists():
        return []
    source_id = int(source["id"])
    marks = ", ".join("?" for _ in ids)
    with _hybrid(source["db_path"]) as conn:
        rows = conn.execute(
            f"{_SELECT} WHERE m.id IN ({marks}) ORDER BY m.id DESC",
            (source_id, source_id, *ids),
        ).fetchall()
    return [_decorate(dict(r), source) for r in rows]


def fetch_all(
    source: dict,
    filters: Filters,
    max_rows: int = 5000,
    batch: int = 1000,
) -> tuple[list[dict], int]:
    """Collect up to *max_rows* matching messages (for exports and queues)."""
    collected: list[dict] = []
    page = 1
    total = 0
    while len(collected) < max_rows:
        rows, total = search(source, filters, page=page, page_size=batch)
        if not rows:
            break
        collected.extend(rows)
        page += 1
    return collected[:max_rows], total


def get_message(source: dict, message_id: int) -> dict | None:
    """Fetch a single message by its primary key (no text search involved)."""
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        return None
    source_id = int(source["id"])
    with _hybrid(source["db_path"]) as conn:
        row = conn.execute(
            f"{_SELECT} WHERE m.id = ? LIMIT 1", (source_id, source_id, int(message_id))
        ).fetchone()
    return _decorate(dict(row), source) if row else None


def distinct_senders(source: dict, limit: int = 500) -> list[str]:
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        if not source.get("json_path"):
            return []
        names = {
            str(m.get("sender_name"))
            for m in content.load_json(source["json_path"])
            if m.get("sender_name")
        }
        return sorted(names)[:limit]
    with _hybrid(source["db_path"]) as conn:
        rows = conn.execute(
            "SELECT DISTINCT sender_name FROM src.messages "
            "WHERE sender_name IS NOT NULL AND sender_name != '' "
            "ORDER BY sender_name COLLATE NOCASE LIMIT ?",
            (limit,),
        ).fetchall()
    return [r[0] for r in rows]


def date_bounds(source: dict) -> tuple[str | None, str | None]:
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        if not source.get("json_path"):
            return None, None
        dates = sorted(str(m.get("date") or "")[:10] for m in content.load_json(source["json_path"]))
        dates = [d for d in dates if d]
        return (dates[0], dates[-1]) if dates else (None, None)
    with _hybrid(source["db_path"]) as conn:
        row = conn.execute(
            "SELECT MIN(date), MAX(date) FROM src.messages"
        ).fetchone()
    return (str(row[0])[:10] if row[0] else None, str(row[1])[:10] if row[1] else None)


def media_type_counts(source: dict) -> dict[str, int]:
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        return {}
    with _hybrid(source["db_path"]) as conn:
        rows = conn.execute(
            "SELECT COALESCE(media_type, 'text') AS t, COUNT(*) AS c "
            "FROM src.messages GROUP BY 1 ORDER BY c DESC"
        ).fetchall()
    return {r["t"]: int(r["c"]) for r in rows}


__all__ = [
    "Filters",
    "search",
    "fetch_all",
    "get_message",
    "get_messages_by_ids",
    "distinct_senders",
    "date_bounds",
    "media_type_counts",
    "MEDIA_TYPES",
    "PROGRESS_STATUSES",
]
