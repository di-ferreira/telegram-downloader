from __future__ import annotations

import os
from pathlib import Path

from config import REPO_ROOT


def repo_root() -> Path:
    return REPO_ROOT


def to_posix(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def media_key(root: Path, media_path: str | None) -> str | None:
    """Normalise a stored ``media_path`` into a path relative to *root*.

    ``backup.py`` stores paths relative to the CWD it was launched from
    (usually ``<repo>/downloads/media/...``), but the value may also be
    absolute or relative to another folder.  Returns ``None`` when the file
    cannot be placed under *root*.
    """
    if not media_path:
        return None

    raw = str(media_path)
    p = Path(raw)

    if p.is_absolute():
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return None

    posix = to_posix(raw)
    candidate = Path(REPO_ROOT) / posix
    try:
        return candidate.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        pass

    parts = [seg for seg in posix.split("/") if seg not in ("", ".")]
    root_name = Path(root).name
    if root_name in parts:
        return "/".join(parts[parts.index(root_name) + 1:])
    if "media" in parts:
        return "/".join(parts[parts.index("media"):])
    return posix


def resolve_media(root: Path, key: str | None) -> Path | None:
    if not key:
        return None
    base = Path(root).resolve()
    target = (base / key).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_file() else None


def human_size(num: float | int | None) -> str:
    if num is None:
        return "-"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def folder_size(path: Path, limit_files: int | None = None) -> tuple[int, int]:
    """Return ``(files, bytes)`` for a folder, tolerating unreadable entries."""
    files = 0
    total = 0
    if not path.is_dir():
        return 0, 0
    for dirpath, _dirnames, filenames in os.walk(path, onerror=lambda _e: None):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
            files += 1
            if limit_files is not None and files >= limit_files:
                return files, total
    return files, total
