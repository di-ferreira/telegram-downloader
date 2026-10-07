"""Autenticação interativa do Telegram — cria o arquivo ``.session``.

O frontend não consegue fazer o 1º login (telefone + código) dentro de um job,
porque o processo roda sem terminal. Este script roda à mão uma vez e deixa a
sessão pronta para ``backup/`` e ``restore/``.

Uso (na raiz do repositório):

    python frontend/login.py            # sessão de backup
    python frontend/login.py restore    # mesma sessão, valida também o restore
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from core import envfile, preflight

DEFAULT_SESSION = envfile.DEFAULTS["SESSION_NAME"]


async def login(session: str, api_id: int, api_hash: str, phone: str | None) -> Path:
    from telethon import TelegramClient

    target = preflight.session_path(session)
    target.parent.mkdir(parents=True, exist_ok=True)
    base = Path(str(target)[: -len(".session")])
    client = TelegramClient(str(base), api_id, api_hash)
    await client.start(phone=phone or None)
    me = await client.get_me()
    await client.disconnect()
    print(f"OK — sessão {target.name} (conta: {me.username or me.first_name} id={me.id})")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria a sessão do Telegram interativamente.")
    parser.add_argument("tool", nargs="?", choices=("backup", "restore"), default="backup")
    args = parser.parse_args()

    values = envfile.read()
    api_id = int(values.get("API_ID") or 0)
    api_hash = (values.get("API_HASH") or "").strip()
    session = (values.get("SESSION_NAME") or "").strip() or DEFAULT_SESSION
    phone = (values.get("PHONE") or "").strip()

    if not api_id or not api_hash:
        print(f"ERRO — API_ID/API_HASH ausentes no `.env` ({envfile.ENV_PATH}).")
        print("Preencha na página Configurações do frontend e rode de novo.")
        return 2

    target = preflight.session_path(session)
    if target.exists():
        print(f"Sessão já existe: {target}")
        return 0

    print(f"Autenticando para a sessão `{session}` (ferramenta: {args.tool})...")
    if args.tool == "restore" and not phone:
        print("Aviso — PHONE não está no `.env`; o Telethon vai pedir o número.")
    try:
        asyncio.run(login(session, api_id, api_hash, phone))
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return 130
    print("Pronto. Rode agora os jobs pelo frontend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
