from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


FRONTEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = FRONTEND_DIR.parent

LIBRARY_DB = Path(os.getenv("FRONTEND_LIBRARY_DB", str(FRONTEND_DIR / "library.db")))
LOG_DIR = Path(os.getenv("FRONTEND_LOG_DIR", str(FRONTEND_DIR / "logs")))

# Loopback only. Never expose the media server outside this machine.
MEDIA_HOST = "127.0.0.1"
MEDIA_PORT = _env_int("FRONTEND_MEDIA_PORT", 0)

PAGE_SIZE = _env_int("FRONTEND_PAGE_SIZE", 50)
WATCHED_AT = _env_float("FRONTEND_WATCHED_AT", 0.95)
AUTO_SCAN = _env_bool("FRONTEND_AUTO_SCAN", True)

# Where "find backups in this project" starts scanning.
SCAN_ROOTS: tuple[Path, ...] = (REPO_ROOT,)

MEDIA_TYPES = ("photo", "video", "document", "audio", "gif", "sticker")
PROGRESS_STATUSES = ("new", "in_progress", "watched", "skipped")

# Maximum bytes read from a job log on every poll.
LOG_TAIL_BYTES = 64 * 1024
