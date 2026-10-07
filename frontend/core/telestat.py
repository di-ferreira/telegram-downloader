"""Tamanho estimado de canais no Telegram (amostra das últimas mensagens).

O ``channels.txt`` não traz tamanho nenhum e o backup não expõe o total do canal
antes de baixar. Aqui a gente puxa o total de mensagens (1 RPC) e soma os bytes
de uma amostra recente (1–2 RPCs) para extrapolar um valor aproximado (``≈``).
O resultado fica em ``frontend/.cache/channel_sizes.json`` para não repetir a
consulta a cada visita.

Limitações: fotos entram como 0 B (a API só expõe o tamanho de documentos) e o
valor é uma extrapolão — serve para decidir se cabe no disco, não para contabilidade.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from core import sessions

CACHE_PATH = Path(__file__).resolve().parents[1] / ".cache" / "channel_sizes.json"
DEFAULT_SAMPLE = 200


def estimate_bytes(total: int, sample_n: int, sample_bytes: int) -> int:
    """Média da amostra extrapolada para ``total`` mensagens."""
    if total <= 0 or sample_n <= 0:
        return 0
    return int(round(sample_bytes / sample_n * total))


def load_cache() -> dict[str, Any]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cached(key: str) -> dict[str, Any] | None:
    entry = load_cache().get(str(key))
    return entry if isinstance(entry, dict) else None


def store(key: str, entry: dict[str, Any]) -> Path:
    data = load_cache()
    data[str(key)] = entry
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_name(CACHE_PATH.name + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, CACHE_PATH)
    return CACHE_PATH


def entity_ref(row: dict[str, str]) -> str | int:
    """``@username`` quando existe; senão o id numérico (``-100...``)."""
    username = str(row.get("username") or "").strip()
    if username and username != "-":
        return username if username.startswith("@") else f"@{username}"
    return int(row.get("id"))


async def _resolve(client: Any, ref: str | int) -> Any:
    try:
        return await client.get_entity(ref)
    except (ValueError, TypeError):
        if isinstance(ref, str):
            raise
        # id cru que a sessão não conhece: procura nos diálogos (mesmo fallback
        # do backup.py para CHANNEL=-100...)
        bare = abs(int(ref))
        async for dialog in client.iter_dialogs():
            if getattr(dialog.entity, "id", None) == bare:
                return dialog.entity
        raise ValueError(f"Canal `{ref}` não está nos diálogos da sessão.")


async def _estimate(ref: str | int, sample: int) -> dict[str, Any]:
    _, client = await sessions.open_authorized()
    try:
        entity = await _resolve(client, ref)
        total = int((await client.get_messages(entity, limit=0)).total or 0)
        sample_n = 0
        sample_bytes = 0
        photos = 0
        async for msg in client.iter_messages(entity, limit=sample):
            sample_n += 1
            document = msg.document
            if document is not None:
                sample_bytes += int(document.size or 0)
            elif msg.photo is not None:
                photos += 1
        return {
            "total": total,
            "sample": sample_n,
            "bytes": sample_bytes,
            "photos": photos,
            "est": estimate_bytes(total, sample_n, sample_bytes),
            "ts": int(time.time()),
        }
    finally:
        await client.disconnect()


def estimate_sync(ref: str | int, sample: int = DEFAULT_SAMPLE) -> dict[str, Any]:
    """Roda a estimativa fora do event loop do Streamlit (bloqueia ~1-3 s)."""
    return asyncio.run(_estimate(ref, sample))
