"""Canais acessíveis (``backup.py --list-channels``) e a pasta de download de cada um.

Cada canal baixado pelo frontend vive em ``OUTPUT_BASE/<título do canal>`` e vira
uma fonte própria — assim Galeria/Reprodutor mostram só aquele canal. O download
grava ``CHANNEL``/``OUTPUT_DIR`` no ``.env`` da raiz e dispara o job.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from core import backend_state, content, envfile, registry

_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SLUG_MAX = 80


def rows() -> list[dict[str, str]]:
    """Parsed ``backup/channels.txt`` (id, type, username, title)."""
    return backend_state.saved_channels()


def filter_rows(items: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    """Substring match over title, username (with/without ``@``) and id.

    Case-insensitive; an empty query returns everything.
    """
    needle = norm(query)
    if not needle:
        return items
    return [
        row
        for row in items
        if any(
            needle in haystack
            for haystack in (
                norm(row.get("title")),
                norm(row.get("username")),
                norm(row.get("id")),
            )
        )
    ]


def norm(value: Any) -> str:
    """Case-insensitive identity: ``@User`` == ``user``."""
    text = str(value or "").strip().lower()
    return text[1:] if text.startswith("@") else text


def channel_key(row: dict[str, str]) -> str:
    """Value written to ``CHANNEL``: the ``@username`` when there is one, else the id."""
    username = str(row.get("username") or "").strip()
    if username and username != "-":
        return username if username.startswith("@") else f"@{username}"
    return str(row.get("id") or "")


def slugify(row: dict[str, str]) -> str:
    """Folder name for a channel: its title, sanitized (fallback: the id)."""
    cleaned = _ILLEGAL.sub(" ", str(row.get("title") or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")[:_SLUG_MAX].strip(" .")
    return cleaned or str(row.get("id") or "canal")


def has_content(folder: Path) -> bool:
    return (folder / "backup.db").exists() or (folder / "messages.json").exists()


def folder_owner(folder: Path) -> str | None:
    """Channel key a previous run left in that folder, if any."""
    source = registry.get_source_by_root(str(folder.resolve()))
    if source and source.get("channel"):
        return str(source["channel"])
    log = folder / "log.txt"
    if log.exists():
        try:
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if "Backing up channel:" in line:
                    return line.split("Backing up channel:", 1)[1].strip()
        except OSError:
            pass
    return None


def _owns(row: dict[str, str], owner_key: str | None) -> bool:
    if not owner_key:
        return True  # empty/unknown folder: reuse it (fresh or failed attempt)
    key = norm(owner_key)
    return key in {norm(channel_key(row)), norm(slugify(row)), norm(row.get("id"))}


def folder_for(row: dict[str, str]) -> Path:
    """Where this channel is (or will be) downloaded.

    Same title as another channel's folder → suffix the id instead of mixing
    two channels in one backup.
    """
    base = envfile.output_base()
    slug = slugify(row)
    folder = base / slug
    if has_content(folder) and not _owns(row, folder_owner(folder)):
        folder = base / f"{slug}_{row['id']}"
    return folder


def find_source(row: dict[str, str]) -> dict | None:
    """Registered source holding this channel's backup, if any."""
    target = str(folder_for(row).resolve())
    key = norm(channel_key(row))
    title = norm(slugify(row))
    for source in registry.list_sources():
        root = str(Path(source["root_path"]).resolve())
        if root == target:
            return source
        names = {
            norm(source.get("channel")),
            norm(source.get("name")),
            norm(Path(source["root_path"]).name),
        }
        if key and key in names:
            return source
        if title and title in names:
            return source
    return None


def is_downloaded(row: dict[str, str]) -> tuple[bool, dict | None]:
    """``(downloaded, source)`` — the source is ``None`` when the folder exists
    but was never registered."""
    source = find_source(row)
    if source:
        return True, source
    folder = folder_for(row)
    return (True, None) if has_content(folder) else (False, None)


def ensure_source(row: dict[str, str]) -> dict | None:
    """Register this channel's folder as a source (does not scan it)."""
    folder = folder_for(row)
    if not has_content(folder):
        return None
    existing = find_source(row)
    if existing:
        return existing
    detection = content.detect(folder)
    if not detection["db_path"] and not detection["json_path"]:
        return None
    return registry.add_source(
        root_path=detection["root_path"],
        name=str(row.get("title") or folder.name),
        channel=channel_key(row),
        db_path_=detection["db_path"],
        json_path=detection["json_path"],
    )


def scan(source: dict, progress: Callable[[str, int, int], None] | None = None) -> dict:
    """Index a freshly downloaded channel (no file hashing — the backup is new)."""
    return content.scan_source(int(source["id"]), verify_files=False, progress=progress)


def prepare(row: dict[str, str]) -> tuple[dict[str, str], Path]:
    """Values to persist in ``.env`` before dispatching the download job."""
    folder = folder_for(row)
    return (
        {
            "CHANNEL": channel_key(row),
            "OUTPUT_DIR": envfile.rel_output_dir(folder),
            "OUTPUT_BASE": envfile.rel_output_dir(envfile.output_base()),
        },
        folder,
    )
