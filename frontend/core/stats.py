from __future__ import annotations

from pathlib import Path
from typing import Any

from core import paths, queries, registry
from core.queries import _hybrid  # shared read-only registry + backup handle


def overview(source: dict) -> dict[str, Any]:
    source_id = int(source["id"])
    progress = registry.progress_summary(source_id)
    counts = queries.media_type_counts(source)
    watched = int(progress.get("watched") or 0)
    tracked = int(progress.get("total") or 0)
    return {
        "messages": int(source.get("message_count") or 0),
        "media": int(source.get("media_count") or 0),
        "bytes": int(source.get("total_bytes") or 0),
        "missing": int(source.get("missing_files") or 0),
        "tracked": tracked,
        "watched": watched,
        "in_progress": int(progress.get("in_progress") or 0),
        "watched_pct": (watched / tracked) if tracked else 0.0,
        "type_counts": counts,
    }


def messages_per_month(source: dict, limit: int = 48) -> list[tuple[str, int]]:
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        return []
    with _hybrid(source["db_path"]) as conn:
        rows = conn.execute(
            """
            SELECT substr(date, 1, 7) AS month, COUNT(*) AS c
            FROM src.messages
            WHERE date IS NOT NULL AND date != ''
            GROUP BY month ORDER BY month DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    data = [(r["month"], int(r["c"])) for r in rows if r["month"]]
    data.sort()
    return data


def top_senders(source: dict, limit: int = 10) -> list[tuple[str, int]]:
    if not source.get("db_path") or not Path(source["db_path"]).exists():
        return []
    with _hybrid(source["db_path"]) as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(sender_name, ''), '(desconhecido)') AS sender, COUNT(*) AS c
            FROM src.messages GROUP BY 1 ORDER BY c DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(r["sender"], int(r["c"])) for r in rows]


def folder_sizes(source: dict) -> list[tuple[str, int, int]]:
    """Return ``(folder, files, bytes)`` per media folder."""
    root = Path(source["root_path"])
    media_root = root / "media"
    results: list[tuple[str, int, int]] = []
    if not media_root.is_dir():
        return results
    for child in sorted(media_root.iterdir()):
        if child.is_dir():
            files, total = paths.folder_size(child)
            results.append((child.name, files, total))
    return results


def totals(sources: list[dict]) -> dict[str, Any]:
    acc = {
        "sources": len([s for s in sources if s.get("enabled")]),
        "messages": 0,
        "media": 0,
        "bytes": 0,
        "missing": 0,
        "tracked": 0,
        "watched": 0,
        "in_progress": 0,
    }
    for source in sources:
        if not source.get("enabled"):
            continue
        info = overview(source)
        acc["messages"] += info["messages"]
        acc["media"] += info["media"]
        acc["bytes"] += info["bytes"]
        acc["missing"] += info["missing"]
        acc["tracked"] += info["tracked"]
        acc["watched"] += info["watched"]
        acc["in_progress"] += info["in_progress"]
    acc["watched_pct"] = (acc["watched"] / acc["tracked"]) if acc["tracked"] else 0.0
    return acc
