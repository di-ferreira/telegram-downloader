"""Verificações que rodam antes de disparar backup/restore.

O backend não tem modo "dry" para autenticação nem para configuração: um
subprocesso sem ``.env``, sem dependências ou sem ``.session`` falha tarde e
sem mensagem útil. Aqui essas falhas viram itens acionáveis na interface.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from config import REPO_ROOT
from core import envfile

DEPENDENCIES = ("telethon", "tqdm", "dotenv")
REQUIREMENTS = {
    "backup": "pip install -r backup/requirements.txt",
    "restore": "pip install -r restore/requirements.txt",
}
LOGIN_CMD = {
    "backup": "python frontend/login.py backup",
    "restore": "python frontend/login.py restore",
}


def _item(level: str, code: str, message: str, fix: str = "") -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "fix": fix}


def missing_dependencies() -> list[str]:
    return [name for name in DEPENDENCIES if importlib.util.find_spec(name) is None]


def session_path(name: str | None = None) -> Path:
    """Absolute path of the Telethon session file (tools resolve it against cwd)."""
    raw = name if name is not None else envfile.session_name()
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return Path(str(path) + ".session")


def _check_env(tool: str) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if not envfile.exists():
        checks.append(
            _item(
                "error",
                "env_missing",
                "Nenhum `.env` na raiz do repositório — o backend falharia em `validate()`.",
                "Criar na página Configurações.",
            )
        )
        return checks
    absent = envfile.missing(tool)
    if absent:
        checks.append(
            _item(
                "error",
                "env_incomplete",
                f"`.env` sem os campos obrigatórios: {', '.join(absent)}.",
                "Preencher na página Configurações.",
            )
        )
    return checks


def _check_deps(tool: str) -> list[dict[str, str]]:
    absent = missing_dependencies()
    if not absent:
        return []
    return [
        _item(
            "error",
            "deps_missing",
            f"Bibliotecas não instaladas: {', '.join(absent)}.",
            REQUIREMENTS[tool],
        )
    ]


def _check_session(tool: str, *, blocking: bool = True) -> list[dict[str, str]]:
    path = session_path()
    if path.exists():
        return []
    level = "error" if blocking else "warn"
    return [
        _item(
            level,
            "session_missing",
            f"Sessão do Telegram inexistente (`{path.name}`): a 1ª execução precisa de "
            "login interativo (telefone + código), e o job roda sem terminal.",
            LOGIN_CMD[tool],
        )
    ]


def for_backup(opts: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Blocking problems for ``backup/backup.py``."""
    opts = opts or {}
    checks = _check_deps("backup")
    checks += _check_env("backup")
    checks += _check_session("backup")
    return checks


def for_restore(opts: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Blocking problems for ``restore/main.py`` (dry-run never logs in)."""
    opts = opts or {}
    dry_run = bool(opts.get("dry_run"))
    checks = _check_deps("restore")
    checks += _check_env("restore")
    checks += _check_session("restore", blocking=not dry_run)

    folder = opts.get("backup_folder")
    if folder:
        path = Path(str(folder))
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            checks.append(
                _item("error", "folder_missing", f"Pasta de backup inexistente: `{path}`.")
            )
        elif not ((path / "backup.db").exists() or (path / "messages.json").exists()):
            checks.append(
                _item(
                    "error",
                    "folder_empty",
                    f"Sem `backup.db` nem `messages.json` em `{path}`.",
                    "Rodar um backup antes.",
                )
            )
    return checks


def validate_restore_opts(opts: dict[str, Any]) -> list[dict[str, str]]:
    """Form-level rules of ``restore/main.py`` (mutual exclusion, retry target)."""
    checks: list[dict[str, str]] = []
    if opts.get("only_media") and opts.get("only_text"):
        checks.append(
            _item("error", "exclusive", "`--only-media` e `--only-text` são mutuamente exclusivos.")
        )
    if opts.get("retry_errors") and not str(opts.get("channel_id") or "").strip():
        checks.append(
            _item("error", "retry_channel", "`--retry-errors` exige `--channel-id`.")
        )
    return checks


def validate_backup_opts(opts: dict[str, Any]) -> list[dict[str, str]]:
    """Form-level rules of ``backup/backup.py``."""
    checks: list[dict[str, str]] = []
    if opts.get("only_media") and opts.get("only_text"):
        checks.append(
            _item("error", "exclusive", "`--only-media` e `--only-text` são mutuamente exclusivos.")
        )
    start, end = opts.get("start_date"), opts.get("end_date")
    if start and end and str(start) > str(end):
        checks.append(_item("error", "date_order", "A data inicial é posterior à final."))
    if opts.get("list_channels") and opts.get("only_media"):
        checks.append(
            _item("warn", "list_ignored", "`--list-channels` ignora os filtros de conteúdo.")
        )
    return checks


def errors(checks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [c for c in checks if c["level"] == "error"]


def report(tool: str) -> list[dict[str, str]]:
    """Human-readable status rows for the settings page."""
    rows = [
        _item(
            "error" if missing_dependencies() else "ok",
            "deps",
            "Bibliotecas do backend"
            + (" ausentes: " + ", ".join(missing_dependencies()) if missing_dependencies() else " instaladas"),
            REQUIREMENTS[tool],
        ),
        _item(
            "error" if not envfile.exists() else ("warn" if envfile.missing(tool) else "ok"),
            "env",
            (
                "Nenhum `.env` na raiz"
                if not envfile.exists()
                else (
                    f"`.env` incompleto: {', '.join(envfile.missing(tool))}"
                    if envfile.missing(tool)
                    else f"`.env` completo para {tool}"
                )
            ),
            "Criar na página Configurações.",
        ),
    ]
    path = session_path()
    rows.append(
        _item(
            "error" if not path.exists() else "ok",
            "session",
            f"Sessão `{path.name}` " + ("presente" if path.exists() else "inexistente (login pendente)"),
            LOGIN_CMD[tool],
        )
    )
    return rows
