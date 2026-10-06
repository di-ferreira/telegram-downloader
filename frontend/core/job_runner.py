from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LOG_DIR, LOG_TAIL_BYTES, REPO_ROOT
from core import registry

_PROCS: dict[int, subprocess.Popen] = {}
_HANDLES: dict[int, Any] = {}
_OFFSETS: dict[int, int] = {}
_CANCELLED: set[int] = set()

_PROGRESS_RE = re.compile(r"Progress:\s*id=(\d+)\s*\|\s*saved=(\d+)")
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)%\|")
_TOTAL_RE = re.compile(r"~\s*(\d+)\s*messages")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reset_interrupted_jobs() -> None:
    """Jobs still marked running belong to a previous app process: we lost the
    handle, so flag them instead of pretending they are alive."""
    for job in registry.list_jobs(limit=200):
        if job.get("status") in ("running", "queued"):
            registry.update_job(job["id"], status="interrupted", finished_at=_now())


# ------------------------------------------------------------------ build


def backup_argv(opts: dict[str, Any]) -> list[str]:
    argv = [sys.executable, str(REPO_ROOT / "backup" / "backup.py")]
    if opts.get("only_media"):
        argv.append("--only-media")
    if opts.get("only_text"):
        argv.append("--only-text")
    if opts.get("start_date"):
        argv += ["--start-date", str(opts["start_date"])]
    if opts.get("end_date"):
        argv += ["--end-date", str(opts["end_date"])]
    media_type = opts.get("media_type") or "all"
    if media_type != "all":
        argv += ["--media-type", media_type]
    if opts.get("skip_existing"):
        argv.append("--skip-existing")
    if not opts.get("resume", True):
        argv.append("--no-resume")
    if opts.get("message_ids"):
        argv.append("--message-id")
        argv += [str(int(i)) for i in opts["message_ids"]]
    if opts.get("list_channels"):
        argv.append("--list-channels")
        if opts.get("save_channels"):
            argv.append("--save")
    return argv


def restore_argv(opts: dict[str, Any]) -> list[str]:
    argv = [sys.executable, str(REPO_ROOT / "restore" / "main.py")]
    if opts.get("backup_folder"):
        argv += ["--backup-folder", str(opts["backup_folder"])]
    if opts.get("start_date"):
        argv += ["--start-date", str(opts["start_date"])]
    if opts.get("end_date"):
        argv += ["--end-date", str(opts["end_date"])]
    if opts.get("start_id"):
        argv += ["--start-id", str(int(opts["start_id"]))]
    if opts.get("end_id"):
        argv += ["--end-id", str(int(opts["end_id"]))]
    if opts.get("only_media"):
        argv.append("--only-media")
    if opts.get("only_text"):
        argv.append("--only-text")
    media_type = opts.get("media_type") or "all"
    if media_type != "all":
        argv += ["--media-type", media_type]
    if opts.get("retry_errors"):
        argv.append("--retry-errors")
        if opts.get("channel_id"):
            argv += ["--channel-id", str(opts["channel_id"])]
    if opts.get("dry_run"):
        argv.append("--dry-run")
    return argv


# ------------------------------------------------------------------ start


def start_job(
    kind: str,
    argv: list[str],
    cwd: Path | str,
    opts: dict[str, Any] | None = None,
    source_id: int | None = None,
    env_extra: dict[str, str] | None = None,
) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    job_id = registry.create_job(
        kind=kind,
        cmd=argv,
        cwd=str(cwd),
        args=opts or {},
        source_id=source_id,
    )
    log_path = LOG_DIR / f"job_{job_id}.log"
    log_path.write_text("", encoding="utf-8")
    registry.update_job(job_id, log_path=str(log_path))

    env = os.environ.copy()
    for key, value in (env_extra or {}).items():
        if value is not None and value != "":
            env[str(key)] = str(value)

    handle = open(log_path, "ab", buffering=0)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
        )
    except OSError as exc:
        handle.close()
        registry.update_job(
            job_id,
            status="failed",
            finished_at=_now(),
            log_tail=f"Falha ao iniciar o processo: {exc}",
        )
        return registry.get_job(job_id) or {}

    _PROCS[job_id] = proc
    _HANDLES[job_id] = handle
    _OFFSETS[job_id] = 0
    registry.update_job(job_id, status="running", pid=proc.pid, started_at=_now())
    return registry.get_job(job_id) or {}


def refresh(job: dict | int) -> dict:
    """Reap a finished process and return the updated job row."""
    job = registry.get_job(job["id"] if isinstance(job, dict) else int(job))
    if not job:
        return {}
    job_id = int(job["id"])
    proc = _PROCS.get(job_id)
    if proc is None:
        return job

    code = proc.poll()
    if code is None:
        return job

    handle = _HANDLES.pop(job_id, None)
    if handle:
        try:
            handle.close()
        except Exception:
            pass
    _PROCS.pop(job_id, None)
    _OFFSETS.pop(job_id, None)

    status = "cancelled" if job_id in _CANCELLED else ("succeeded" if code == 0 else "failed")
    _CANCELLED.discard(job_id)
    registry.update_job(
        job_id,
        status=status,
        exit_code=code,
        finished_at=_now(),
        log_tail=read_tail(job_id)[:4000],
    )
    return registry.get_job(job_id) or {}


def cancel(job_id: int) -> None:
    proc = _PROCS.get(int(job_id))
    if proc is None or proc.poll() is not None:
        return
    _CANCELLED.add(int(job_id))
    try:
        proc.terminate()
    except Exception:
        pass


def is_running(job_id: int) -> bool:
    proc = _PROCS.get(int(job_id))
    return proc is not None and proc.poll() is None


# ------------------------------------------------------------------- logs


def read_tail(job_id: int, max_bytes: int = LOG_TAIL_BYTES) -> str:
    job = registry.get_job(int(job_id))
    if not job or not job.get("log_path"):
        return ""
    path = Path(job["log_path"])
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    start = max(0, size - max_bytes)
    try:
        with open(path, "rb") as fh:
            fh.seek(start)
            raw = fh.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def read_incremental(job_id: int) -> str:
    """Return only the bytes added since the previous call (for a live log)."""
    job = registry.get_job(int(job_id))
    if not job or not job.get("log_path"):
        return ""
    path = Path(job["log_path"])
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    offset = _OFFSETS.get(int(job_id), 0)
    if size < offset:
        offset = 0
    if size == offset:
        return ""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            raw = fh.read(min(size - offset, 256 * 1024))
    except OSError:
        return ""
    _OFFSETS[int(job_id)] = offset + len(raw)
    return raw.decode("utf-8", errors="replace")


def parse_progress(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"percent": None, "saved": None, "total": None, "message": ""}
    if not text:
        return out
    match = _PROGRESS_RE.search(text)
    if match:
        out["saved"] = int(match.group(2))
    percents = _PERCENT_RE.findall(text)
    if percents:
        try:
            out["percent"] = min(float(percents[-1]) / 100.0, 1.0)
        except ValueError:
            pass
    total = _TOTAL_RE.search(text)
    if total:
        out["total"] = int(total.group(1))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines:
        out["message"] = lines[-1].strip()[:300]
    if out["percent"] is None and out["total"] and out["saved"]:
        out["percent"] = min(out["saved"] / out["total"], 1.0)
    return out


def env_preview(path: Path) -> dict[str, str]:
    """Read a ``.env`` file, masking secrets for display."""
    masked: dict[str, str] = {}
    if not path.exists():
        return masked
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return masked
    secret = ("API_HASH", "PHONE", "SESSION_NAME")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if any(s in key for s in secret) and len(value) > 4:
            value = value[:2] + "*" * (len(value) - 4) + value[-2:]
        masked[key] = value
    return masked
