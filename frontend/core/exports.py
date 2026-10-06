from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Iterable

from core import paths

EXPORT_COLUMNS = [
    "id",
    "date",
    "text",
    "sender_id",
    "sender_name",
    "message_type",
    "views",
    "media_path",
    "media_type",
    "file_name",
    "file_size",
    "mime_type",
    "md5_hash",
    "progress_status",
    "progress_percent",
    "is_favorite",
]


def rows_to_csv(rows: Iterable[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or EXPORT_COLUMNS
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c) for c in columns})
    return buffer.getvalue().encode("utf-8-sig")


def rows_to_json(rows: Iterable[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or EXPORT_COLUMNS
    payload = [{c: row.get(c) for c in columns} for row in rows]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def files_to_zip(
    source: dict,
    rows: Iterable[dict],
    max_files: int = 200,
    max_bytes: int = 512 * 1024 * 1024,
) -> tuple[bytes, int, int]:
    """Zip the media referenced by *rows*.

    Returns ``(payload, included, skipped)``; oversized or missing files are
    skipped rather than aborting the export.
    """
    root = Path(source["root_path"])
    buffer = io.BytesIO()
    included = 0
    skipped = 0
    written = 0
    used: set[str] = set()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            if included >= max_files or written >= max_bytes:
                skipped += 1
                continue
            key = row.get("media_key") or paths.media_key(root, row.get("media_path"))
            target = paths.resolve_media(root, key)
            if target is None:
                skipped += 1
                continue
            try:
                size = target.stat().st_size
            except OSError:
                skipped += 1
                continue
            if written + size > max_bytes:
                skipped += 1
                continue

            name = key or target.name
            if name in used:
                name = f"{target.stem}_{row.get('id', included)}{target.suffix}"
            used.add(name)
            try:
                zf.write(target, arcname=name)
            except OSError:
                skipped += 1
                continue
            included += 1
            written += size

    return buffer.getvalue(), included, skipped
