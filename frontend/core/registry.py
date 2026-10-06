from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import LIBRARY_DB

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    db_path TEXT,
    json_path TEXT,
    channel TEXT,
    enabled INTEGER DEFAULT 1,
    added_at TEXT,
    last_scanned_at TEXT,
    message_count INTEGER DEFAULT 0,
    media_count INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    missing_files INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS media_state (
    source_id INTEGER NOT NULL,
    media_key TEXT NOT NULL,
    message_id INTEGER,
    kind TEXT,
    status TEXT DEFAULT 'new',
    position_sec REAL DEFAULT 0,
    duration_sec REAL DEFAULT 0,
    percent REAL DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    last_played_at TEXT,
    updated_at TEXT,
    note TEXT,
    PRIMARY KEY (source_id, media_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_media_state_message
    ON media_state (source_id, message_id) WHERE message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS favorites (
    source_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    note TEXT,
    created_at TEXT,
    PRIMARY KEY (source_id, message_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_id INTEGER,
    args TEXT,
    cmd TEXT,
    cwd TEXT,
    status TEXT DEFAULT 'queued',
    pid INTEGER,
    exit_code INTEGER,
    started_at TEXT,
    finished_at TEXT,
    log_path TEXT,
    log_tail TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_msg USING fts5(
    source_id UNINDEXED,
    message_id UNINDEXED,
    text,
    sender_name,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    return LIBRARY_DB


def _connect(readonly: bool = False) -> sqlite3.Connection:
    path = Path(LIBRARY_DB)
    if readonly and path.exists():
        uri = "file:" + path.as_posix() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    if readonly:
        conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connect(readonly: bool = False) -> Iterator[sqlite3.Connection]:
    conn = _connect(readonly)
    try:
        yield conn
        if not readonly:
            conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------- sources


def list_sources(enabled_only: bool = False) -> list[dict]:
    with connect(readonly=True) as conn:
        where = "WHERE enabled = 1" if enabled_only else ""
        return _rows(conn, f"SELECT * FROM sources {where} ORDER BY name COLLATE NOCASE")


def get_source(source_id: int | None) -> dict | None:
    if source_id is None:
        return None
    with connect(readonly=True) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None


def get_source_by_root(root_path: str) -> dict | None:
    with connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE root_path = ?", (str(root_path),)
        ).fetchone()
        return dict(row) if row else None


def add_source(
    root_path: str | Path,
    name: str | None = None,
    channel: str | None = None,
    db_path_: str | None = None,
    json_path: str | None = None,
) -> dict | None:
    root = str(Path(root_path).resolve())
    existing = get_source_by_root(root)
    if existing:
        return existing
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO sources (name, root_path, db_path, json_path, channel, enabled, added_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (name or Path(root).name, root, db_path_, json_path, channel, now_iso()),
        )
        source_id = cur.lastrowid
        conn.commit()
    return get_source(source_id)


def update_source(source_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE sources SET {cols} WHERE id = ?", (*fields.values(), source_id))
        conn.commit()


def set_enabled(source_id: int, enabled: bool) -> None:
    update_source(source_id, enabled=1 if enabled else 0)


def delete_source(source_id: int) -> None:
    """Forget a source. Files on disk are never touched."""
    with connect() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM media_state WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM favorites WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM fts_msg WHERE source_id = ?", (source_id,))
        conn.commit()


def mark_scanned(source_id: int, **stats: Any) -> None:
    stats.setdefault("last_scanned_at", now_iso())
    update_source(source_id, **stats)


# ------------------------------------------------------------ media state


def get_media_state(source_id: int, media_key: str) -> dict | None:
    with connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT * FROM media_state WHERE source_id = ? AND media_key = ?",
            (source_id, media_key),
        ).fetchone()
        return dict(row) if row else None


def get_media_state_by_message(source_id: int, message_id: int) -> dict | None:
    if message_id is None:
        return None
    with connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT * FROM media_state WHERE source_id = ? AND message_id = ?",
            (source_id, message_id),
        ).fetchone()
        return dict(row) if row else None


def upsert_media_state(source_id: int, media_key: str, **fields: Any) -> None:
    """Insert or update playback state.

    When ``message_id`` is known the row is keyed by it, guaranteeing at most
    one state row per message (which keeps the message listing 1:1).
    """
    fields = {k: v for k, v in fields.items() if v is not None}
    fields["updated_at"] = now_iso()
    with connect() as conn:
        row = None
        message_id = fields.get("message_id")
        if message_id is not None:
            row = conn.execute(
                "SELECT media_key FROM media_state WHERE source_id = ? AND message_id = ?",
                (source_id, message_id),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT media_key FROM media_state WHERE source_id = ? AND media_key = ?",
                (source_id, media_key),
            ).fetchone()

        if row is None:
            cols = ["source_id", "media_key", *fields.keys()]
            placeholders = ", ".join("?" for _ in cols)
            values = [source_id, media_key, *fields.values()]
            conn.execute(
                f"INSERT INTO media_state ({', '.join(cols)}) VALUES ({placeholders})",
                values,
            )
        else:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE media_state SET {sets} WHERE source_id = ? AND media_key = ?",
                (*fields.values(), source_id, row["media_key"]),
            )
        conn.commit()


def set_status(source_id: int, media_key: str, status: str, **fields: Any) -> None:
    upsert_media_state(source_id, media_key, status=status, **fields)


def list_progress(source_id: int, statuses: tuple[str, ...], limit: int = 50) -> list[dict]:
    marks = ", ".join("?" for _ in statuses)
    with connect(readonly=True) as conn:
        return _rows(
            conn,
            f"""
            SELECT * FROM media_state
            WHERE source_id = ? AND status IN ({marks})
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (source_id, *statuses, limit),
        )


def progress_summary(source_id: int) -> dict:
    with connect(readonly=True) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'watched' THEN 1 ELSE 0 END) AS watched,
                   SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress
            FROM media_state WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
    return dict(row)


# --------------------------------------------------------------- favorites


def is_favorite(source_id: int, message_id: int) -> bool:
    with connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE source_id = ? AND message_id = ?",
            (source_id, message_id),
        ).fetchone()
    return row is not None


def toggle_favorite(source_id: int, message_id: int, note: str | None = None) -> bool:
    """Return True when the message is a favorite after the call."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE source_id = ? AND message_id = ?",
            (source_id, message_id),
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM favorites WHERE source_id = ? AND message_id = ?",
                (source_id, message_id),
            )
            conn.commit()
            return False
        conn.execute(
            "INSERT INTO favorites (source_id, message_id, note, created_at) VALUES (?, ?, ?, ?)",
            (source_id, message_id, note, now_iso()),
        )
        conn.commit()
        return True


# -------------------------------------------------------------------- jobs


def create_job(
    kind: str,
    cmd: list[str],
    cwd: str,
    args: dict | None = None,
    source_id: int | None = None,
    log_path: str | None = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (kind, source_id, args, cmd, cwd, status, started_at, log_path)
            VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (
                kind,
                source_id,
                json.dumps(args or {}, ensure_ascii=False),
                json.dumps(cmd, ensure_ascii=False),
                cwd,
                now_iso(),
                log_path,
            ),
        )
        job_id = cur.lastrowid
        conn.commit()
    return int(job_id)


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
        conn.commit()


def get_job(job_id: int) -> dict | None:
    with connect(readonly=True) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict]:
    with connect(readonly=True) as conn:
        return _rows(conn, "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- search


def fts_replace(source_id: int, rows: list[tuple[int, str, str | None]], batch: int = 1000) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM fts_msg WHERE source_id = ?", (source_id,))
        payload = [(source_id, msg_id, text or "", sender or "") for msg_id, text, sender in rows]
        for start in range(0, len(payload), batch):
            conn.executemany(
                "INSERT INTO fts_msg (source_id, message_id, text, sender_name) VALUES (?, ?, ?, ?)",
                payload[start : start + batch],
            )
        conn.commit()


def fts_available(source_id: int) -> bool:
    with connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM fts_msg WHERE source_id = ?", (source_id,)
        ).fetchone()
    return bool(row and row[0])
