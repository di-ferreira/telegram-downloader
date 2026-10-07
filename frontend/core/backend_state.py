"""Estado que ``backup/`` e ``restore/`` deixam em disco — leitura apenas.

Tudo aqui é derivado do backend: artefatos do backup, ``channels.txt`` do
``--list-channels``, ``restore_progress.db``, os três logs do restore e o
resumo impresso por ``--dry-run``. Nada é escrito por este módulo.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from config import REPO_ROOT
from core import envfile
from core.paths import human_size

CHANNELS_PATH = REPO_ROOT / "backup" / "channels.txt"
RESTORE_PROGRESS_PATH = REPO_ROOT / "restore_progress.db"
RESTORE_LOGS = {
    "restore": REPO_ROOT / "logs" / "restore.log",
    "errors": REPO_ROOT / "logs" / "errors.log",
    "missing_media": REPO_ROOT / "logs" / "missing_media.log",
}

_JSON_MAX_BYTES = 64 * 1024 * 1024
_DRY_RUN_RE = re.compile(
    r"^(Total messages|With media|Text only|Total media size|Missing media files):\s*(.+?)\s*$"
)


# --------------------------------------------------------------- backup out


def output_dir() -> Path:
    return envfile.output_dir()


def _count_db(path: Path) -> str | None:
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            return f"{conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]:,} mensagens"
        finally:
            conn.close()
    except Exception:
        return None


def _count_json(path: Path, size: int) -> str | None:
    if size > _JSON_MAX_BYTES:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return f"{len(data):,} mensagens" if isinstance(data, list) else None


def _count_files(path: Path, limit: int = 200_000) -> str | None:
    total = 0
    bytes_ = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                total += 1
                try:
                    bytes_ += child.stat().st_size
                except OSError:
                    pass
                if total >= limit:
                    break
    except OSError:
        return None
    return f"{total:,} arquivos · {human_size(bytes_)}"


def backup_artifacts() -> list[dict[str, Any]]:
    root = output_dir()
    rows: list[dict[str, Any]] = []

    def add(label: str, path: Path, detailer=None) -> None:
        exists = path.exists()
        size = None
        mtime = None
        if exists:
            try:
                stat = path.stat()
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                exists = False
        detail = None
        if exists and detailer:
            detail = detailer(path, size or 0)
        rows.append(
            {
                "label": label,
                "path": path,
                "exists": exists,
                "size": size,
                "mtime": mtime,
                "detail": detail,
            }
        )

    add("backup.db", root / "backup.db", lambda p, s: _count_db(p))
    add("messages.json", root / "messages.json", lambda p, s: _count_json(p, s))
    add("messages.csv", root / "messages.csv")
    add("log.txt", root / "log.txt")
    add("media/", root / "media", lambda p, s: _count_files(p) if p.is_dir() else None)
    add("channels.txt", CHANNELS_PATH)
    return rows


# --------------------------------------------------------------- channels


def parse_channels(text: str) -> list[dict[str, str]]:
    """Parse the table printed by ``backup.py --list-channels``."""
    out: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("ID "):
            continue
        parts = stripped.split(None, 3)
        if len(parts) < 2 or not re.fullmatch(r"-?\d+", parts[0]):
            continue
        out.append(
            {
                "id": parts[0],
                "type": parts[1],
                "username": parts[2] if len(parts) > 2 else "-",
                "title": parts[3] if len(parts) > 3 else "",
            }
        )
    return out


def saved_channels() -> list[dict[str, str]]:
    if not CHANNELS_PATH.exists():
        return []
    return parse_channels(CHANNELS_PATH.read_text(encoding="utf-8", errors="replace"))


# --------------------------------------------------------------- restore


def restore_progress() -> dict[str, Any]:
    empty = {"total": 0, "counts": {}, "errors": [], "last_sent": None}
    if not RESTORE_PROGRESS_PATH.exists():
        return empty
    try:
        conn = sqlite3.connect(
            f"file:{RESTORE_PROGRESS_PATH.as_posix()}?mode=ro", uri=True, timeout=5
        )
        conn.row_factory = sqlite3.Row
    except Exception:
        return empty
    try:
        counts = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT status, COUNT(*) FROM progress GROUP BY status ORDER BY status"
            )
        }
        total = sum(counts.values())
        errors = [
            dict(row)
            for row in conn.execute(
                "SELECT message_id_original, message_id_novo, status, tentativas, erro, data_envio "
                "FROM progress WHERE status = 'error' ORDER BY message_id_original LIMIT 200"
            )
        ]
        last = conn.execute(
            "SELECT MAX(message_id_original) FROM progress WHERE status = 'sent'"
        ).fetchone()[0]
        return {"total": total, "counts": counts, "errors": errors, "last_sent": last}
    except Exception:
        return empty
    finally:
        conn.close()


def restore_logs() -> dict[str, Path]:
    return RESTORE_LOGS


# --------------------------------------------------------------- dry run


def parse_dry_run(text: str) -> dict[str, Any] | None:
    """Parse the summary printed by ``restore/main.py --dry-run``."""
    if not text or "DRY RUN" not in text:
        return None
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _DRY_RUN_RE.match(line.strip())
        if match:
            found[match.group(1)] = match.group(2)
    if not found:
        return None
    missing_files: list[str] = []
    capture = False
    for line in text.splitlines():
        if line.strip().startswith("Missing files:"):
            capture = True
            continue
        if capture:
            if line.startswith("  - "):
                missing_files.append(line[4:].strip())
            elif line.strip() and not line.startswith("  "):
                capture = False
    total = found.get("Total messages", "0")
    return {
        "total": _as_int(total),
        "with_media": _as_int(found.get("With media", "0")),
        "text_only": _as_int(found.get("Text only", "0")),
        "size_label": found.get("Total media size", "—"),
        "missing": _as_int(found.get("Missing media files", "0")),
        "missing_files": missing_files,
    }


def _as_int(raw: str | None) -> int:
    try:
        return int(str(raw).split()[0])
    except (TypeError, ValueError, IndexError):
        return 0


def read_tail(path: Path, max_bytes: int = 64 * 1024) -> str:
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            return fh.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""
