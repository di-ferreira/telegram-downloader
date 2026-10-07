"""Leitura e gravação do ``.env`` da raiz — a configuração efetiva do backend.

``backup/config.py`` e ``restore/config.py`` leem ``Path.cwd()/".env"`` antes do
próprio diretório, e os jobs rodam com ``cwd=<raiz do repositório>``. Logo o
arquivo da raiz é o que vale para as duas ferramentas.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from config import REPO_ROOT

ENV_PATH = REPO_ROOT / ".env"
EXAMPLE_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "backup" / ".env.example",
    REPO_ROOT / "restore" / ".env.example",
)

# Valores que nunca aparecem inteiros na interface.
SECRET_KEYS = ("API_HASH", "PHONE")

# Textos vindos dos ``.env.example``: contam como "não preenchido".
PLACEHOLDERS: dict[str, set[str]] = {
    "API_ID": {"123456"},
    "API_HASH": {"your_api_hash_here"},
    "CHANNEL": {"@channel_username"},
    "PHONE": {"+5511999999999"},
    "CHANNEL_NAME": {"My Restored Channel"},
}

BACKUP_REQUIRED = ("API_ID", "API_HASH", "CHANNEL")
BACKUP_OPTIONAL = ("OUTPUT_DIR", "CONCURRENT_DOWNLOADS", "SESSION_NAME")
RESTORE_REQUIRED = ("API_ID", "API_HASH", "PHONE", "CHANNEL_NAME")
RESTORE_OPTIONAL = ("CHANNEL_DESCRIPTION", "CHANNEL_USERNAME", "BACKUP_FOLDER", "SESSION_NAME")

# Os dois exemplos trazem SESSION_NAME com valores diferentes; como o ``.env``
# da raiz é único, vale um nome compartilhado (uma autenticação para tudo).
DEFAULTS: dict[str, str] = {
    "OUTPUT_DIR": "downloads",
    "CONCURRENT_DOWNLOADS": "5",
    "SESSION_NAME": "telegram_session",
    "BACKUP_FOLDER": "downloads",
    "CHANNEL_DESCRIPTION": "",
    "CHANNEL_USERNAME": "",
}


def mask(key: str, value: str) -> str:
    """Mask a secret for display; short values are replaced entirely."""
    if key not in SECRET_KEYS:
        return value
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def exists() -> bool:
    return ENV_PATH.exists()


def read() -> dict[str, str]:
    """Raw (unmasked) values, keys in file order."""
    if not ENV_PATH.exists():
        return {}
    return parse(ENV_PATH.read_text(encoding="utf-8", errors="replace"))


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def preview() -> dict[str, str]:
    """Values ready for display: secrets masked."""
    return {key: mask(key, value) for key, value in read().items()}


def defaults() -> dict[str, str]:
    """Template values with the shared-session defaults applied."""
    merged: dict[str, str] = {}
    for path in EXAMPLE_PATHS:
        if path.exists():
            merged.update(parse(path.read_text(encoding="utf-8", errors="replace")))
    merged.update(DEFAULTS)
    return merged


def get(key: str, default: str = "") -> str:
    return read().get(key, default) or default


def session_name() -> str:
    return get("SESSION_NAME") or DEFAULTS["SESSION_NAME"]


def output_dir() -> Path:
    raw = get("OUTPUT_DIR") or DEFAULTS["OUTPUT_DIR"]
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path)


def backup_folder() -> Path:
    raw = get("BACKUP_FOLDER") or DEFAULTS["BACKUP_FOLDER"]
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path)


def is_placeholder(key: str, value: str) -> bool:
    return value.strip() in PLACEHOLDERS.get(key, set())


def missing(tool: str) -> list[str]:
    """Required keys that are absent, empty or still a template placeholder."""
    required = BACKUP_REQUIRED if tool == "backup" else RESTORE_REQUIRED
    values = read()
    return [key for key in required if not (values.get(key) or "").strip() or is_placeholder(key, values[key])]


def write(values: dict[str, Any]) -> Path:
    """Merge ``values`` into the root ``.env`` atomically.

    Existing comments and unknown keys are preserved; the previous file is
    kept as ``.env.bak``. Never pass masked values here.
    """
    clean = {
        str(key): str(value).replace("\r", " ").replace("\n", " ").strip()
        for key, value in values.items()
        if value is not None
    }
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        shutil.copy2(ENV_PATH, ENV_PATH.parent / (ENV_PATH.name + ".bak"))
    else:
        lines = _template_lines()
        # O primeiro ``SESSION_NAME`` vem do backup; o arquivo é único, então
        # vale o nome compartilhado até o usuário escolher outro.
        clean.setdefault("SESSION_NAME", DEFAULTS["SESSION_NAME"])
    text = _render(lines, clean)
    tmp = ENV_PATH.parent / (ENV_PATH.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, ENV_PATH)
    return ENV_PATH


def ensure() -> Path:
    """Create the root ``.env`` from the tool templates when it is missing."""
    if not ENV_PATH.exists():
        return write({})
    return ENV_PATH


def _template_lines() -> list[str]:
    lines = [
        "# Gerado pelo frontend — configuração efetiva de backup/ e restore/.",
        "# Os dois scripts leem este arquivo porque rodam com cwd = raiz do repositório.",
        "",
    ]
    for path in EXAMPLE_PATHS:
        lines.append(f"# --- {path.parent.name}/.env.example ---")
        if path.exists():
            lines += path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines.append("")
    return lines


def _render(lines: list[str], values: dict[str, str]) -> str:
    out: list[str] = []
    emitted: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, current = line.partition("=")
            key = key.strip()
            if key:
                if key in emitted:  # duplicate key across the two templates
                    continue
                emitted.add(key)
                out.append(f"{key}={values.get(key, current.strip())}")
                continue
        out.append(line)
    for key, value in values.items():
        if key not in emitted:
            out.append(f"{key}={value}")
    return "\n".join(out).rstrip("\n") + "\n"
