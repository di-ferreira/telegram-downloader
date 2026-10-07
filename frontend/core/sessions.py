"""Sessões Telethon: descobre qual dos arquivos ``.session`` está autorizado.

Dois históricos convivem neste repo: o fluxo manual do backup gravou a sessão
autorizada em ``backup/`` (cwd da época), enquanto os jobs do frontend rodam com
cwd na raiz — onde um ``SESSION_NAME`` relativo resolve para
``<raiz>/<nome>.session``. Aqui testamos os candidatos e devolvemos o primeiro
que autentica, para:

- leituras rápidas (a estimativa de tamanho em ``telestat``), e
- o ``SESSION_NAME`` (absoluto) dos jobs despachados — sem isso o backup
  falharia com "sessão sem login" mesmo existindo uma sessão boa em ``backup/``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from config import REPO_ROOT
from core import envfile, preflight

_PICKED: str | None = None


def bases() -> list[str]:
    """Bases Telethon (sem ``.session``) candidatas: raiz, ``backup/``, ``restore/``."""
    name = Path(envfile.session_name()).name
    return [
        str(preflight.session_path(name))[: -len(".session")],
        str(REPO_ROOT / "backup" / name),
        str(REPO_ROOT / "restore" / name),
    ]


async def open_authorized() -> tuple[str, Any]:
    """Primeira sessão autorizada: ``(base, client conectado)``.

    Levanta ``RuntimeError`` quando faltam credenciais ou nenhuma sessão presta;
    nesse caso o caller é quem traduz o erro para o usuário.
    """
    from telethon import TelegramClient  # import local: mantém o módulo leve

    values = envfile.read()
    api_id = int(values.get("API_ID") or 0)
    api_hash = (values.get("API_HASH") or "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("API_ID/API_HASH ausentes no `.env` — preencha em Configurações.")

    tried: list[Path] = []
    for base in bases():
        session_file = Path(base + ".session")
        if not session_file.exists():
            continue
        tried.append(session_file)
        client = TelegramClient(base, api_id, api_hash)
        authorized = False
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
        finally:
            if not authorized:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001 - falha ao fechar não pode mascarar o erro real
                    pass
        if authorized:
            return base, client

    if tried:
        names = ", ".join(f"`{p}`" for p in tried)
        raise RuntimeError(f"Sessão sem login ({names}) — rode `python frontend/login.py backup`.")
    raise RuntimeError("Nenhuma sessão `.session` encontrada — rode `python frontend/login.py backup`.")


async def _pick() -> str | None:
    try:
        base, client = await open_authorized()
    except RuntimeError:
        return None
    await client.disconnect()
    return base


def pick_authorized_base() -> str | None:
    """Base da sessão autorizada, cacheada no processo (só acertos são memoizados).

    Sem rede/sessão utilizável devolve ``None`` — o job segue sem a injeção e o
    log dele expõe o erro, como antes.
    """
    global _PICKED
    if _PICKED:
        return _PICKED
    try:
        base = asyncio.run(_pick())
    except Exception:  # noqa: BLE001 - rede fora não pode travar o despacho
        return None
    if base:
        _PICKED = base
    return base
