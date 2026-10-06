from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterator

from core import paths, registry

CONTENT_COLUMNS = (
    "id",
    "date",
    "text",
    "sender_id",
    "sender_name",
    "message_type",
    "views",
    "media_path",
    "media_type",
    "file_name",
    "file_size",
    "mime_type",
    "md5_hash",
)


def detect(root: Path) -> dict[str, Any]:
    """Find ``backup.db`` / ``messages.json`` inside a backup folder."""
    root = Path(root)
    db = root / "backup.db"
    js = root / "messages.json"
    channel = None
    if db.exists():
        channel = _guess_channel(db)
    return {
        "root_path": str(root.resolve()) if root.exists() else str(root),
        "db_path": str(db) if db.exists() else None,
        "json_path": str(js) if js.exists() else None,
        "channel": channel,
    }


def _guess_channel(db_path: Path) -> str | None:
    """Best-effort channel name from the side-car files written by backup.py."""
    for name in ("channels.txt", "log.txt"):
        candidate = Path(db_path).parent / name
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if "Backing up channel:" in line:
                return line.split("Backing up channel:", 1)[1].strip()
    return None


def open_content(db_path: str | Path) -> sqlite3.Connection:
    """Open a backup database strictly read-only."""
    uri = "file:" + Path(db_path).as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def iter_messages(db_path: str | Path, batch: int = 1000) -> Iterator[dict]:
    conn = open_content(db_path)
    try:
        cur = conn.execute("SELECT * FROM messages ORDER BY id")
        while True:
            rows = cur.fetchmany(batch)
            if not rows:
                break
            for row in rows:
                yield dict(row)
    finally:
        conn.close()


def load_json(path: str | Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def message_columns(db_path: str | Path) -> list[str]:
    conn = open_content(db_path)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    finally:
        conn.close()


def count_messages(source: dict) -> int:
    if source.get("db_path"):
        conn = open_content(source["db_path"])
        try:
            return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        finally:
            conn.close()
    if source.get("json_path"):
        return len(load_json(source["json_path"]))
    return 0


def scan_source(
    source_id: int,
    verify_files: bool = True,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Refresh counts, rebuild the full-text index and (optionally) verify files.

    Never writes to the backup itself - only to ``library.db``.
    """
    source = registry.get_source(source_id)
    if not source:
        raise ValueError(f"Unknown source {source_id}")

    root = Path(source["root_path"])
    stats: dict[str, Any] = {
        "message_count": 0,
        "media_count": 0,
        "total_bytes": 0,
        "missing_files": 0,
    }
    fts_rows: list[tuple[int, str, str | None]] = []

    if source.get("db_path") and Path(source["db_path"]).exists():
        messages = iter_messages(source["db_path"])
    elif source.get("json_path") and Path(source["json_path"]).exists():
        messages = iter(load_json(source["json_path"]))
    else:
        registry.mark_scanned(
            source_id,
            message_count=0,
            media_count=0,
            total_bytes=0,
            missing_files=0,
        )
        registry.fts_replace(source_id, [])
        return stats

    for index, msg in enumerate(messages, start=1):
        stats["message_count"] += 1
        fts_rows.append((int(msg.get("id") or 0), msg.get("text") or "", msg.get("sender_name")))

        key = paths.media_key(root, msg.get("media_path"))
        if not key:
            continue
        stats["media_count"] += 1
        if verify_files:
            target = paths.resolve_media(root, key)
            if target is None:
                stats["missing_files"] += 1
            else:
                try:
                    stats["total_bytes"] += target.stat().st_size
                except OSError:
                    stats["missing_files"] += 1
        if progress and index % 500 == 0:
            progress("Indexando mensagens...", index, 0)

    if progress:
        progress("Construindo índice de busca...", stats["message_count"], 0)
    registry.fts_replace(source_id, fts_rows)
    registry.mark_scanned(source_id, **stats)
    return stats


def find_backup_folders(roots: tuple[Path, ...]) -> list[Path]:
    """Locate folders holding ``backup.db`` or ``messages.json``."""
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not Path(root).is_dir():
            continue
        for dirpath, dirnames, filenames in _walk(Path(root)):
            names = set(filenames)
            if "backup.db" in names or "messages.json" in names:
                key = str(Path(dirpath).resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(Path(dirpath))
                # no need to descend into a backup folder
                dirnames[:] = [d for d in dirnames if d not in ("media",)]
            else:
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d not in (".git", "venv", ".venv", "node_modules", "__pycache__", ".vscode")
                ]
    return sorted(found)


def _walk(root: Path):
    import os

    return os.walk(root, onerror=lambda _e: None)
